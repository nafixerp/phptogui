"""Point Card Points Report — port of PointCardPointsReportController::data.

For each point-card customer (``clients.pcard`` set), per applicable subgroup,
computes sales weight/amount in the period and the loyalty points earned from
the ``pcardtable`` rule (points = base / valuefor1point, base = weight or amount
per ``pointbasedon``; rounded down when the rule says so), the point value, and
the closing balance = opening + earned − redeemed (``salesm.redmpoints``).
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from ...core.db import Database
from ...core.decimals import money, quantize, to_decimal, weight as wq

_ZERO = Decimal("0")
_PT = Decimal("0.01")


class PointCardPointsService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = max(1, int(rlevel or 1))

    def _col(self, t: str, c: str) -> bool:
        return self.db.table_exists(t) and self.db.column_exists(t, c)

    def report(self, date1: str, date2: str, pcard: str = "") -> dict:
        empty = {"rows": [], "totals": {"count": 0, "spoints": _ZERO, "pointvalue": _ZERO,
                                        "clpoints": _ZERO}}
        if not (self.db.table_exists("clients") and self.db.table_exists("pcardtable")
                and self.db.table_exists("pcard")):
            return empty
        rules = {f"{str(r.get('pcard') or '').strip()}|{str(r.get('isubgrp') or '').strip()}": r
                 for r in self.db.fetchall("SELECT * FROM pcardtable")}
        pcard_subgrps: dict[str, list[str]] = {}
        for key in rules:
            p, sg = key.split("|", 1)
            pcard_subgrps.setdefault(p.strip(), []).append(sg.strip())
        names = {str(r.get("code") or "").strip(): str(r.get("name") or "").strip()
                 for r in self.db.fetchall("SELECT code, name FROM pcard")}

        opcol = "oppcardpoints" if self._col("clients", "oppcardpoints") else None
        where = ["pcard IS NOT NULL", "TRIM(pcard) <> ''"]
        params: dict = {}
        if pcard.strip():
            where.append("pcard = :pc"); params["pc"] = pcard.strip()
        clients = self.db.fetchall(
            f"SELECT code, name, pcard{(', ' + opcol) if opcol else ''} FROM clients "
            f"WHERE {' AND '.join(where)} ORDER BY code LIMIT 5000", params)

        has_redm = self._col("salesm", "redmpoints")
        has_sd = self.db.table_exists("salesd") and self.db.table_exists("salesm")
        has_subgrp = self._col("items", "subgrpcode")
        rows = []
        for cl in clients:
            ccode = str(cl.get("code") or "").strip()
            cpcard = str(cl.get("pcard") or "").strip()
            oppoints = to_decimal(cl.get(opcol)) if opcol else _ZERO
            redeemed = _ZERO
            if has_redm and has_sd:
                redeemed = to_decimal(self.db.scalar(
                    "SELECT COALESCE(SUM(redmpoints),0) FROM salesm WHERE custcode = :c "
                    "AND tdate BETWEEN :f AND :t AND control <= :g",
                    {"c": ccode, "f": date1, "t": date2, "g": self.rlevel}))
            for subgrp in pcard_subgrps.get(cpcard, [""]):
                rule = rules.get(f"{cpcard}|{subgrp}")
                pointbasedon = str((rule or {}).get("pointbasedon") or "A").strip().upper()
                v1 = to_decimal((rule or {}).get("valuefor1point")) or _ZERO
                vpp = to_decimal((rule or {}).get("valueperpoint")) or _ZERO
                rounddown = int((rule or {}).get("rounddown") or 0)
                swgt = samt = _ZERO
                if has_sd:
                    agg = self._sales(ccode, date1, date2, subgrp if (has_subgrp and subgrp) else None)
                    swgt, samt = agg
                spoints = _ZERO
                if v1 > 0:
                    base = swgt if pointbasedon == "W" else samt
                    spoints = base / v1
                    spoints = spoints.quantize(Decimal("1"), rounding=ROUND_DOWN) if rounddown else quantize(spoints, _PT)
                pointvalue = quantize(spoints * vpp, _PT)
                clpoints = quantize(oppoints + spoints - redeemed, _PT)
                rows.append({
                    "code": ccode, "name": str(cl.get("name") or "").strip(),
                    "pcardname": names.get(cpcard, cpcard), "isubgrp": subgrp,
                    "pointbasedon": "Weight" if pointbasedon == "W" else "Amount",
                    "swgt": wq(swgt), "samt": money(samt), "spoints": spoints,
                    "pointvalue": pointvalue, "redeem": redeemed, "oppoints": oppoints,
                    "clpoints": clpoints, "clpointvalue": quantize(clpoints * vpp, _PT)})
        tot = {"count": len(rows), "spoints": sum((r["spoints"] for r in rows), _ZERO),
               "pointvalue": sum((r["pointvalue"] for r in rows), _ZERO),
               "clpoints": sum((r["clpoints"] for r in rows), _ZERO)}
        return {"rows": rows, "totals": tot}

    def _sales(self, ccode: str, date1: str, date2: str, subgrp: str | None):
        if subgrp:
            r = self.db.fetchone(
                "SELECT COALESCE(SUM(d.weight),0) AS w, COALESCE(SUM(d.amount),0) AS a "
                "FROM salesd d JOIN salesm m ON m.slno=d.slno JOIN items i ON i.code=d.code "
                "WHERE m.custcode=:c AND m.tdate BETWEEN :f AND :t AND m.control<=:g AND i.subgrpcode=:sg",
                {"c": ccode, "f": date1, "t": date2, "g": self.rlevel, "sg": subgrp}) or {}
        else:
            r = self.db.fetchone(
                "SELECT COALESCE(SUM(d.weight),0) AS w, COALESCE(SUM(d.amount),0) AS a "
                "FROM salesd d JOIN salesm m ON m.slno=d.slno "
                "WHERE m.custcode=:c AND m.tdate BETWEEN :f AND :t AND m.control<=:g",
                {"c": ccode, "f": date1, "t": date2, "g": self.rlevel}) or {}
        return wq(r.get("w")), money(r.get("a"))
