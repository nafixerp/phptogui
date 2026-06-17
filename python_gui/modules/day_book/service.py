"""Day Book (read-only) — port of DayBookController core.

Cash balance: base = accountm.CASH opbal (gilevel 1) or opbalb; opening = base +
SUM(daybook.amount for CASH, control<=gilevel, tdate<from); closing = base +
SUM(... tdate<=to). Detailed entries (Form 3) list daybook rows in the range
with account name + voucher number; negative amount = debit, positive = credit.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money


class DayBookService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = int(gilevel or 1)

    def _cash_base(self) -> Decimal:
        col = "opbal" if self.gilevel == 1 else "opbalb"
        v = self.db.scalar(f"SELECT {col} FROM accountm WHERE accode = 'CASH' LIMIT 1")
        return money(v)

    def _cash_sum(self, op: str, dt: str) -> Decimal:
        v = self.db.scalar(
            f"SELECT COALESCE(SUM(amount),0) FROM daybook "
            f"WHERE accode = 'CASH' AND control <= :g AND tdate {op} :d",
            {"g": self.gilevel, "d": dt},
        )
        return money(v)

    def cash_balances(self, date_from: str, date_to: str) -> dict:
        if not self.db.table_exists("daybook") or not self.db.table_exists("accountm"):
            return {"opbal": Decimal("0"), "clbal": Decimal("0")}
        base = self._cash_base()
        opbal = money(base + self._cash_sum("<", date_from))
        clbal = money(base + self._cash_sum("<=", date_to))
        return {"opbal": opbal, "clbal": clbal}

    def entries(self, date_from: str, date_to: str) -> list[dict]:
        if not self.db.table_exists("daybook"):
            return []
        raw = self.db.fetchall(
            "SELECT d.slno, d.tdate, TRIM(d.accode) AS accode, d.amount, "
            "TRIM(COALESCE(am.name,'')) AS acname, TRIM(COALESCE(dp.vchno,'')) AS vchno, "
            "TRIM(COALESCE(dp.particular,'')) AS particular "
            "FROM daybook d "
            "LEFT JOIN accountm am ON TRIM(d.accode) = TRIM(am.accode) "
            "LEFT JOIN daybookpart dp ON d.slno = dp.slno "
            "WHERE d.tdate BETWEEN :f AND :t AND d.control <= :g "
            "ORDER BY d.tdate, d.slno",
            {"f": date_from, "t": date_to, "g": self.gilevel},
        )
        out = []
        for r in raw:
            amount = money(r.get("amount"))
            out.append({
                "date": str(r.get("tdate") or ""), "vchno": str(r.get("vchno") or ""),
                "accode": str(r.get("accode") or ""), "acname": str(r.get("acname") or ""),
                "particular": str(r.get("particular") or ""),
                "debit": (-amount) if amount < 0 else Decimal("0"),
                "credit": amount if amount > 0 else Decimal("0"),
            })
        return out
