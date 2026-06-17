"""Account Ledger (read-only) — port of AccountLedgerController core.

Opening balance = accountm.opbal (gilevel 1) or opbalb, PLUS sum of daybook.amount
for the account before date-from with control <= gilevel. Ledger rows join
daybook+daybookpart in the date range (control <= gilevel); negative amount =
debit, positive = credit; running balance = opening + signed amounts.

(Opposite-account multi-splits and rate/weight columns from the controller are
enhancements not reproduced here; the single opposite account name is shown.)
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money


class AccountLedgerService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = int(gilevel or 1)

    def account(self, code: str) -> dict | None:
        return self.db.fetchone(
            "SELECT TRIM(accode) AS accode, TRIM(name) AS name, TRIM(actype2) AS actype2, "
            "opbal, opbalb FROM accountm WHERE TRIM(accode) = :c LIMIT 1", {"c": code.strip()},
        )

    def opening_balance(self, code: str, date_from: str) -> Decimal:
        acc = self.account(code)
        if not acc:
            return Decimal("0")
        base = money(acc.get("opbal") if self.gilevel == 1 else acc.get("opbalb"))
        prior = Decimal("0")
        if self.db.table_exists("daybook"):
            v = self.db.scalar(
                "SELECT COALESCE(SUM(amount), 0) FROM daybook "
                "WHERE TRIM(accode) = :c AND tdate < :d AND control <= :g",
                {"c": code.strip(), "d": date_from, "g": self.gilevel},
            )
            prior = money(v)
        return money(base + prior)

    def ledger(self, code: str, date_from: str, date_to: str) -> dict:
        code = str(code or "").strip()
        opening = self.opening_balance(code, date_from)
        rows: list[dict] = []
        if self.db.table_exists("daybook") and self.db.table_exists("daybookpart"):
            raw = self.db.fetchall(
                "SELECT d.slno, d.tdate, d.amount, "
                "TRIM(COALESCE(dp.vchno,'')) AS vchno, "
                "TRIM(COALESCE(dp.particular,'')) AS particular, "
                "TRIM(COALESCE(d.opaccode,'')) AS opaccode, "
                "TRIM(COALESCE(oth.name,'')) AS othacname "
                "FROM daybook d JOIN daybookpart dp ON d.slno = dp.slno "
                "LEFT JOIN accountm oth ON TRIM(d.opaccode) = TRIM(oth.accode) "
                "WHERE TRIM(d.accode) = :c AND d.tdate BETWEEN :f AND :t AND d.control <= :g "
                "ORDER BY d.tdate, d.slno",
                {"c": code, "f": date_from, "t": date_to, "g": self.gilevel},
            )
            running = opening
            for r in raw:
                amount = money(r.get("amount"))
                running = money(running + amount)
                rows.append({
                    "date": str(r.get("tdate") or ""), "vchno": str(r.get("vchno") or ""),
                    "othacname": str(r.get("othacname") or r.get("opaccode") or ""),
                    "particular": str(r.get("particular") or ""),
                    "debit": (-amount) if amount < 0 else Decimal("0"),
                    "credit": amount if amount > 0 else Decimal("0"),
                    "running_balance": running.copy_abs(),
                    "running_side": "Dr" if running < 0 else "Cr",
                })
        closing = rows[-1]["running_balance"] if rows else opening.copy_abs()
        closing_side = rows[-1]["running_side"] if rows else ("Dr" if opening < 0 else "Cr")
        return {"opening": opening.copy_abs(), "opening_side": "Dr" if opening < 0 else "Cr",
                "rows": rows, "closing": closing, "closing_side": closing_side}
