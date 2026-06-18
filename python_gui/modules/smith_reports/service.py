"""Smith (goldsmith/jeweller) reports — Transaction Summary and W&A Summary.

Both iterate clients of a given ``ctype`` (joined to ``clientsgs``) and pull
smith movement from ``smithd``+``smithm`` by ``givrec`` (G = issued, R =
received). Weights are ``smithd.netwgt``; making charge / stone / wastage from
the detail; party cash movement from ``daybook``.

- ``trans_summary``: in-period received/issued weight, wastage, making charge,
  stone amount, and paid amount (abs of negative daybook). Port of
  SmithTransSummaryController.
- ``wa_summary``: cumulative received/issued weight up to a date, pending
  weight, last issue/receive dates and running cash balance. Port of
  SmithWaSummaryController.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, weight as wq

_ZERO = Decimal("0")


class SmithReportsService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = max(1, int(rlevel or 1))

    def _ready(self) -> bool:
        return (self.db.table_exists("clients") and self.db.table_exists("clientsgs")
                and self.db.table_exists("smithm") and self.db.table_exists("smithd"))

    def _smith_sum(self, code: str, col: str, givrec: str | None, date1: str | None, date2: str) -> Decimal:
        where = ["sm.smithcode = :c", "sm.control <= :g", "sm.tdate <= :t2"]
        params: dict = {"c": code, "g": self.rlevel, "t2": date2}
        if givrec:
            where.append("sd.givrec = :gr"); params["gr"] = givrec
        if date1:
            where.append("sm.tdate >= :t1"); params["t1"] = date1
        v = self.db.scalar(
            f"SELECT COALESCE(SUM(sd.{col}),0) FROM smithd sd JOIN smithm sm ON sm.slno = sd.slno "
            f"WHERE {' AND '.join(where)}", params)
        return money(v) if col in ("mcharge", "stoneprice", "wastage") else wq(v)

    def _clients(self, ctype: str) -> list[dict]:
        return self.db.fetchall(
            "SELECT TRIM(c.code) AS code, TRIM(c.name) AS name FROM clients c "
            "JOIN clientsgs gs ON gs.code = c.code WHERE c.ctype = :ct ORDER BY c.name LIMIT 5000",
            {"ct": ctype})

    def trans_summary(self, date1: str, date2: str, ctype: str = "G") -> list[dict]:
        if not self._ready():
            return []
        has_db = self.db.table_exists("daybook")
        out = []
        for c in self._clients(ctype):
            code = str(c.get("code") or "").strip()
            rcvd = self._smith_sum(code, "netwgt", "R", date1, date2)
            issued = self._smith_sum(code, "netwgt", "G", date1, date2)
            wastage = self._smith_sum(code, "wastage", "R", date1, date2)
            mcharge = self._smith_sum(code, "mcharge", None, date1, date2)
            stamt = self._smith_sum(code, "stoneprice", None, date1, date2)
            paid = _ZERO
            if has_db:
                paid = money(self.db.scalar(
                    "SELECT COALESCE(SUM(amount),0) FROM daybook WHERE accode = :c AND control <= :g "
                    "AND amount < 0 AND tdate >= :t1 AND tdate <= :t2",
                    {"c": code, "g": self.rlevel, "t1": date1, "t2": date2}))
            out.append({
                "code": code, "name": str(c.get("name") or "").strip(),
                "rcvdwgt": rcvd, "issuedwgt": issued, "pendwgt": wq(issued - rcvd),
                "wastage": wastage, "mcharge": mcharge, "stamt": stamt,
                "mcstamt": money(mcharge + stamt), "paidamt": money(abs(paid)),
            })
        return out

    def wa_summary(self, as_of: str, ctype: str = "G") -> list[dict]:
        if not self._ready():
            return []
        has_db = self.db.table_exists("daybook")
        out = []
        for c in self._clients(ctype):
            code = str(c.get("code") or "").strip()
            rcvd = self._smith_sum(code, "netwgt", "R", None, as_of)
            issued = self._smith_sum(code, "netwgt", "G", None, as_of)
            lastissue = self.db.scalar(
                "SELECT MAX(sm.tdate) FROM smithd sd JOIN smithm sm ON sm.slno = sd.slno "
                "WHERE sm.smithcode = :c AND sd.givrec = 'G' AND sm.control <= :g AND sm.tdate <= :t",
                {"c": code, "g": self.rlevel, "t": as_of})
            tranamt = _ZERO
            if has_db:
                tranamt = money(self.db.scalar(
                    "SELECT COALESCE(SUM(amount),0) FROM daybook WHERE accode = :c AND control <= :g AND tdate <= :t",
                    {"c": code, "g": self.rlevel, "t": as_of}))
            out.append({
                "code": code, "name": str(c.get("name") or "").strip(),
                "rcvdwgt": rcvd, "issuedwgt": issued, "pendwgt": wq(issued - rcvd),
                "lastissue": str(lastissue or ""), "tranamt": tranamt,
            })
        return out
