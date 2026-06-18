"""Order reports — Process (pending) list and Returns register.

- ``pending_process``: open orders (``orderm.status = 1``, control <= gilevel)
  with total advance = advance + eamt + sretamt and the customer mobile.
  Port of OrderProcessController.
- ``returns``: orders that have been billed out, joined ``orderm.salebill`` →
  ``salesm.billno`` over a sale-date range. Port of OrderReturnsController.
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import money

PENDING_STATUS = 1


class OrderReportsService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = max(1, int(gilevel or 1))

    def _col(self, t: str, c: str) -> bool:
        return self.db.table_exists(t) and self.db.column_exists(t, c)

    def pending_process(self) -> list[dict]:
        if not self.db.table_exists("orderm"):
            return []
        rows = self.db.fetchall(
            "SELECT slno, TRIM(ordno) AS ordno, tdate, duedate, custcode, "
            "TRIM(COALESCE(custname,'')) AS custname, COALESCE(billamt,0) AS billamt, "
            "COALESCE(advance,0) AS advance, COALESCE(eamt,0) AS eamt, "
            "COALESCE(sretamt,0) AS sretamt "
            "FROM orderm WHERE control <= :g AND status = :s ORDER BY slno",
            {"g": self.gilevel, "s": PENDING_STATUS})
        mobiles = {}
        if self.db.table_exists("clients") and rows:
            codes = sorted({str(r.get("custcode") or "").strip() for r in rows if r.get("custcode")})
            if codes:
                ph = ", ".join(f":c{i}" for i in range(len(codes)))
                mr = self.db.fetchall(
                    f"SELECT TRIM(code) AS code, mobile FROM clients WHERE TRIM(code) IN ({ph})",
                    {f"c{i}": v for i, v in enumerate(codes)})
                mobiles = {r["code"]: str(r.get("mobile") or "").strip() for r in mr}
        out = []
        for r in rows:
            tadv = money(money(r["advance"]) + money(r["eamt"]) + money(r["sretamt"]))
            out.append({
                "ordno": str(r["ordno"]), "tdate": str(r.get("tdate") or ""),
                "duedate": str(r.get("duedate") or ""), "custname": str(r["custname"]),
                "billamt": money(r["billamt"]), "tadv": tadv,
                "mobile": mobiles.get(str(r.get("custcode") or "").strip(), ""),
            })
        return out

    def returns(self, date1: str, date2: str) -> list[dict]:
        if not (self.db.table_exists("orderm") and self.db.table_exists("salesm")):
            return []
        return self.db.fetchall(
            "SELECT TRIM(orderm.ordno) AS ordno, orderm.tdate AS ord_tdate, orderm.duedate, "
            "TRIM(COALESCE(orderm.custname,'')) AS custname, COALESCE(orderm.billamt,0) AS ord_billamt, "
            "COALESCE(orderm.advance,0) AS ord_advance, orderm.smcode, "
            "salesm.billno AS salebill, salesm.tdate AS sale_tdate, COALESCE(salesm.billamt,0) AS sale_billamt "
            "FROM orderm JOIN salesm ON orderm.salebill = salesm.billno "
            "WHERE orderm.control <= :g AND salesm.tdate BETWEEN :f AND :t "
            "ORDER BY orderm.tdate LIMIT 2000",
            {"g": self.gilevel, "f": date1, "t": date2})
