"""Day Summary (read-only) — daybook debit/credit totals grouped by date.

Source: DaySummaryController. Per date in the range (control <= rlevel): total
debit (negative amounts) and total credit (positive amounts), with a net column.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money


class DaySummaryService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = int(rlevel or 1)

    def summary(self, date_from: str, date_to: str) -> dict:
        if not self.db.table_exists("daybook"):
            return {"rows": [], "total_debit": money(0), "total_credit": money(0)}
        rows = self.db.fetchall(
            "SELECT tdate, "
            "COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END),0) AS debit, "
            "COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END),0) AS credit "
            "FROM daybook WHERE tdate BETWEEN :f AND :t AND control <= :g "
            "GROUP BY tdate ORDER BY tdate",
            {"f": date_from, "t": date_to, "g": self.rlevel})
        out, td, tc = [], Decimal("0"), Decimal("0")
        for r in rows:
            d = money(r["debit"]); c = money(r["credit"])
            td += d; tc += c
            out.append({"date": str(r["tdate"]), "debit": d, "credit": c, "net": money(c - d)})
        return {"rows": out, "total_debit": money(td), "total_credit": money(tc)}
