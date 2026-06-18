"""Sales misc reports — Delivery Status and Value-Addition Check List.

- ``delivery_status``: per sale bill with delivery status (D/L/A/P), net gold
  weight, and the receivable balance. Port of DeliveryStatusReportController.
- ``va_check``: period value-addition totals over sales —
  va amount = Σ(mcharge + wastage*rate), and average VA% =
  Σ((mcharge/weight/rate)*100) over lines with rate>0 & weight>0, plus
  wastage / stone / discount. Port of VACheckListController sales aggregates.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, quantize, weight as wq

_ZERO = Decimal("0")
_PCT = Decimal("0.01")
_DSTATUS = {"delivered": "D", "locker": "L", "anamath": "A"}


class SalesMiscReportsService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = max(1, int(rlevel or 1))

    def _col(self, t: str, c: str) -> bool:
        return self.db.table_exists(t) and self.db.column_exists(t, c)

    def delivery_status(self, date1: str, date2: str, reptype: str = "") -> list[dict]:
        if not self.db.table_exists("salesm"):
            return []
        dstatus = "m.dstatus" if self._col("salesm", "dstatus") else "'' AS dstatus"
        goldwgt = "0 AS goldwgt"
        if self.db.table_exists("salesd") and self.db.table_exists("items"):
            goldwgt = ("(SELECT COALESCE(SUM(sd.weight - sd.stonewgt),0) FROM salesd sd "
                       "JOIN items it ON it.code = sd.code WHERE sd.slno = m.slno AND it.itype='G') AS goldwgt")
        where = ["m.tdate BETWEEN :f AND :t"]
        params: dict = {"f": date1, "t": date2, "g": self.rlevel}
        if self._col("salesm", "control"):
            where.append("m.control <= :g")
        if self._col("salesm", "opbill"):
            where.append("(m.opbill <> 1 OR m.opbill IS NULL)")
        if reptype in _DSTATUS and self._col("salesm", "dstatus"):
            where.append("m.dstatus = :ds"); params["ds"] = _DSTATUS[reptype]
        elif reptype == "pending" and self._col("salesm", "dstatus"):
            where.append("(m.dstatus IS NULL OR m.dstatus = '' OR m.dstatus = 'P')")
        rows = self.db.fetchall(
            f"SELECT m.slno, m.tdate, m.billno, m.custname, COALESCE(m.billamt,0) AS billamt, "
            f"COALESCE(m.eamt,0) AS eamt, COALESCE(m.sretamt,0) AS sretamt, "
            f"COALESCE(m.discount,0) AS discount, m.smcode, {dstatus}, {goldwgt} "
            f"FROM salesm m WHERE {' AND '.join(where)} ORDER BY m.tdate, m.slno LIMIT 5000", params)
        out = []
        for r in rows:
            billamt = money(r.get("billamt"))
            bal = money(billamt - money(r.get("eamt")) - money(r.get("sretamt")) - money(r.get("discount")))
            out.append({"slno": r.get("slno"), "tdate": str(r.get("tdate") or ""),
                        "billno": str(r.get("billno") or ""), "custname": str(r.get("custname") or ""),
                        "billamt": billamt, "balance": bal, "smcode": str(r.get("smcode") or ""),
                        "dstatus": str(r.get("dstatus") or "") or "P", "goldwgt": wq(r.get("goldwgt"))})
        return out

    def va_check(self, date1: str, date2: str) -> dict:
        if not (self.db.table_exists("salesd") and self.db.table_exists("salesm")):
            return {"weight": _ZERO, "wastage": _ZERO, "mcharge": _ZERO, "vaamt": _ZERO,
                    "stoneprice": _ZERO, "stonewgt": _ZERO, "disc": _ZERO, "tvaperc": _ZERO}
        agg = self.db.fetchone(
            "SELECT COALESCE(SUM(d.weight),0) AS weight, COALESCE(SUM(d.wastage),0) AS wastage, "
            "COALESCE(SUM(d.mcharge),0) AS mcharge, "
            "COALESCE(SUM(d.mcharge + (d.wastage * d.rate)),0) AS vaamt, "
            "COALESCE(SUM(d.stoneprice),0) AS stoneprice, COALESCE(SUM(d.stonewgt),0) AS stonewgt "
            "FROM salesd d JOIN salesm m ON m.slno = d.slno "
            "WHERE m.tdate BETWEEN :f AND :t AND m.control <= :g",
            {"f": date1, "t": date2, "g": self.rlevel}) or {}
        disc = self.db.scalar(
            "SELECT COALESCE(SUM(discount),0) FROM salesm WHERE tdate BETWEEN :f AND :t AND control <= :g",
            {"f": date1, "t": date2, "g": self.rlevel})
        tvaperc = self.db.scalar(
            "SELECT COALESCE(SUM(d.mcharge * 100.0 / d.weight / d.rate),0) FROM salesd d "
            "JOIN salesm m ON m.slno = d.slno WHERE m.tdate BETWEEN :f AND :t AND m.control <= :g "
            "AND d.rate > 0 AND d.weight > 0",
            {"f": date1, "t": date2, "g": self.rlevel})
        return {"weight": wq(agg.get("weight")), "wastage": wq(agg.get("wastage")),
                "mcharge": money(agg.get("mcharge")), "vaamt": money(agg.get("vaamt")),
                "stoneprice": money(agg.get("stoneprice")), "stonewgt": wq(agg.get("stonewgt")),
                "disc": money(disc), "tvaperc": quantize(tvaperc, _PCT)}
