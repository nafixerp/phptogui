"""Sales reports (read-only) — net sales, monthly, salesman-wise, check list.

Source: NetSalesReportController / MonthlySalesReportController /
SalesmanCategoryReportController / SalesCheckListController. Date-range reads over
`salesm` (control <= rlevel), column-guarded so missing amount columns default to
0. Optional salesman (smcode) filter.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money

# candidate amount columns on salesm
_AMTS = ["billamt", "eamt", "staxamt", "discount", "sretamt", "netamt"]


class SalesReportsService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = int(rlevel or 1)

    def _cols(self) -> set[str]:
        return set(self.db.columns("salesm")) if self.db.table_exists("salesm") else set()

    def _amt_cols(self) -> list[str]:
        cols = self._cols()
        return [c for c in _AMTS if c in cols]

    def _where(self, date1: str, date2: str, smcode: str):
        cols = self._cols()
        where, params = ["1=1"], {}
        if "tdate" in cols:
            where.append("tdate BETWEEN :f AND :t"); params.update(f=date1, t=date2)
        if "control" in cols:
            where.append("control <= :g"); params["g"] = self.rlevel
        if smcode.strip() and "smcode" in cols:
            where.append("UPPER(TRIM(smcode)) = :sm"); params["sm"] = smcode.strip().upper()
        return " AND ".join(where), params, cols

    def net_sales(self, date1: str, date2: str, smcode: str = "") -> dict:
        if not self.db.table_exists("salesm"):
            return {"totals": {}, "count": 0}
        where, params, cols = self._where(date1, date2, smcode)
        amt = self._amt_cols()
        sums = ", ".join(f"COALESCE(SUM({c}),0) AS {c}" for c in amt)
        sel = (sums + ", " if sums else "") + "COUNT(*) AS cnt"
        row = self.db.fetchone(f"SELECT {sel} FROM salesm WHERE {where}", params) or {}
        totals = {c: money(row.get(c)) for c in amt}
        return {"totals": totals, "count": int(row.get("cnt") or 0)}

    def monthly_sales(self, date1: str, date2: str, smcode: str = "") -> list[dict]:
        if not self.db.table_exists("salesm"):
            return []
        where, params, cols = self._where(date1, date2, smcode)
        amt = self._amt_cols()
        sums = ", ".join(f"COALESCE(SUM({c}),0) AS {c}" for c in amt)
        rows = self.db.fetchall(
            f"SELECT SUBSTR(tdate,1,7) AS ym, COUNT(*) AS cnt{(', ' + sums) if sums else ''} "
            f"FROM salesm WHERE {where} GROUP BY SUBSTR(tdate,1,7) ORDER BY ym", params)
        return [{"month": str(r["ym"]), "count": int(r["cnt"]),
                 **{c: money(r.get(c)) for c in amt}} for r in rows]

    def salesman_wise(self, date1: str, date2: str) -> list[dict]:
        if not self.db.table_exists("salesm") or "smcode" not in self._cols():
            return []
        where, params, cols = self._where(date1, date2, "")
        amt = self._amt_cols()
        sums = ", ".join(f"COALESCE(SUM({c}),0) AS {c}" for c in amt)
        rows = self.db.fetchall(
            f"SELECT TRIM(COALESCE(smcode,'')) AS smcode, COUNT(*) AS cnt{(', ' + sums) if sums else ''} "
            f"FROM salesm WHERE {where} GROUP BY TRIM(COALESCE(smcode,'')) ORDER BY smcode", params)
        return [{"smcode": str(r["smcode"] or "(none)"), "count": int(r["cnt"]),
                 **{c: money(r.get(c)) for c in amt}} for r in rows]

    def check_list(self, date1: str, date2: str, smcode: str = "") -> list[dict]:
        if not self.db.table_exists("salesm"):
            return []
        where, params, cols = self._where(date1, date2, smcode)
        status = "status" if "status" in cols else "NULL"
        net = "netamt" if "netamt" in cols else ("billamt" if "billamt" in cols else "0")
        rows = self.db.fetchall(
            f"SELECT slno, billno, tdate, TRIM(COALESCE(custname,'')) AS custname, "
            f"COALESCE({net},0) AS netamt, {status} AS status FROM salesm WHERE {where} "
            f"ORDER BY tdate, slno LIMIT 1000", params)
        return rows
