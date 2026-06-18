"""Party reports (read-only) — customer/supplier outstanding balances.

Balance per party = accountm.opbal + SUM(daybook.amount) for the account
(control <= rlevel). Negative balance shows as Dr, positive as Cr (daybook sign
convention). Filters by party type via clients.ctype.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money


class PartyReportsService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = int(rlevel or 1)

    def outstanding(self, ctype: str = "C", search: str = "") -> dict:
        if not self.db.table_exists("clients") or not self.db.table_exists("accountm"):
            return {"rows": [], "total_dr": money(0), "total_cr": money(0)}
        ctype = (ctype or "C").strip().upper()
        sql = ("SELECT TRIM(c.code) AS code, TRIM(c.name) AS name, "
               "COALESCE(a.opbal,0) AS opbal FROM clients c "
               "JOIN accountm a ON TRIM(c.code) = TRIM(a.accode) WHERE c.ctype = :t")
        params = {"t": ctype}
        if search.strip():
            params["s"] = f"%{search.strip()}%"
            sql += " AND (TRIM(c.code) LIKE :s OR TRIM(c.name) LIKE :s)"
        sql += " ORDER BY c.name LIMIT 500"
        clients = self.db.fetchall(sql, params)

        rows, total_dr, total_cr = [], Decimal("0"), Decimal("0")
        has_daybook = self.db.table_exists("daybook")
        for c in clients:
            bal = money(c.get("opbal"))
            if has_daybook:
                bal += money(self.db.scalar(
                    "SELECT COALESCE(SUM(amount),0) FROM daybook WHERE TRIM(accode) = :a AND control <= :g",
                    {"a": c["code"], "g": self.rlevel}))
            bal = money(bal)
            if bal == 0:
                continue
            side = "Dr" if bal < 0 else "Cr"
            if bal < 0:
                total_dr += bal.copy_abs()
            else:
                total_cr += bal
            rows.append({"code": c["code"], "name": c["name"],
                         "balance": bal.copy_abs(), "side": side})
        return {"rows": rows, "total_dr": money(total_dr), "total_cr": money(total_cr)}
