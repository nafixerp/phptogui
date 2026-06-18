"""Sales/Purchase registers (read-only) — date-range listing of bill masters.

A generic register over salesm / salesrm / purchasem / purchaserm: lists bills in
a date range (control <= rlevel) with billno, date, party name and the amount
columns that exist, plus column totals. Column-guarded so it adapts to each
master's actual schema (SalesRegisterController uses the same column-exists
fallback).
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money

# candidate amount columns, in display order
_AMOUNT_COLS = ["billamt", "discount", "staxamt", "sgst", "cgst", "igst", "astamt", "netamt"]


class RegisterService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = int(rlevel or 1)

    def register(self, master: str, name_col: str, date_from: str, date_to: str) -> dict:
        if not self.db.table_exists(master):
            return {"rows": [], "totals": {}, "amount_cols": []}
        cols = set(self.db.columns(master))
        amount_cols = [c for c in _AMOUNT_COLS if c in cols]
        name_expr = f"TRIM(COALESCE({name_col}, ''))" if name_col in cols else "''"

        selects = ["slno", "billno" if "billno" in cols else "slno AS billno",
                   "tdate" if "tdate" in cols else "NULL AS tdate", f"{name_expr} AS party"]
        selects += [f"COALESCE({c}, 0) AS {c}" for c in amount_cols]
        where = "1=1"
        params: dict = {}
        if "tdate" in cols:
            where += " AND tdate BETWEEN :f AND :t"
            params.update(f=date_from, t=date_to)
        if "control" in cols:
            where += " AND control <= :g"
            params["g"] = self.rlevel
        order = "tdate, slno" if "tdate" in cols else "slno"

        rows = self.db.fetchall(
            f"SELECT {', '.join(selects)} FROM {master} WHERE {where} ORDER BY {order}", params)
        totals = {c: money(0) for c in amount_cols}
        for r in rows:
            for c in amount_cols:
                totals[c] = money(totals[c] + money(r.get(c)))
        return {"rows": rows, "totals": totals, "amount_cols": amount_cols}
