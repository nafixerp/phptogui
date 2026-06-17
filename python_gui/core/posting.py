"""Double-entry posting engine — shared by Receipt/Payment/Journal (Phase 4+).

Source of truth: docs/accounting-posting-logic.md + ReceiptController /
PaymentController. Invariants enforced/relied upon:

  * daybook.amount sign: NEGATIVE = debit, POSITIVE = credit; a complete
    transaction (one slno) sums to zero.
  * slno is reserved from generali.SERIALNO but never below max(slno) across all
    transaction tables (nextSerialNo).
  * Voucher numbers come from generali counters, de-duped against existing
    daybookpart.vchno (reserveVoucherWithCounter).

All writes are column-filtered to the live schema and run inside a caller
transaction (db.transaction()).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .db import Database, Tx

# Tables scanned for the max existing slno (nextSerialNo).
_SLNO_TABLES = ["salesm", "salesrm", "purchasem", "purchaserm", "daybook",
                "daybookpart", "orderm", "smithm", "refinerym", "repairm"]


class PostingEngine:
    def __init__(self, database: Database):
        self.db = database

    # -- generali counters --------------------------------------------------
    def gen_int(self, code: str) -> int:
        if not self.db.table_exists("generali"):
            return 0
        v = self.db.scalar("SELECT cvalue FROM generali WHERE code = :c LIMIT 1", {"c": code})
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0

    def _set_generali(self, tx: Tx, code: str, value: int) -> None:
        res = tx.execute("UPDATE generali SET cvalue = :v WHERE code = :c", {"v": value, "c": code})
        if getattr(res, "rowcount", 0) == 0:
            tx.execute("INSERT INTO generali (code, cvalue) VALUES (:c, :v)", {"c": code, "v": value})

    def increment_gen_int(self, tx: Tx, code: str) -> int:
        """Port of incrementGenInt() — current+1, persisted (no vchno de-dupe)."""
        nxt = self.gen_int(code) + 1
        self._set_generali(tx, code, nxt)
        return nxt

    # -- serial / voucher numbers ------------------------------------------
    def next_serial_no(self, tx: Tx) -> int:
        """Port of nextSerialNo() — max(SERIALNO, max slno across tables) + 1."""
        current = self.gen_int("SERIALNO")
        max_used = 0
        for table in _SLNO_TABLES:
            if self.db.table_exists(table) and self.db.column_exists(table, "slno"):
                v = tx.scalar(f"SELECT MAX(slno) FROM {table}")
                if v is not None:
                    max_used = max(max_used, int(v))
        nxt = max(current, max_used) + 1
        self._set_generali(tx, "SERIALNO", nxt)
        return nxt

    def last_voucher_number_for_prefix(self, prefix: str) -> int:
        if prefix == "" or not self.db.table_exists("daybookpart") or not self.db.column_exists("daybookpart", "vchno"):
            return 0
        rows = self.db.fetchall(
            "SELECT vchno FROM daybookpart WHERE vchno IS NOT NULL AND vchno LIKE :p",
            {"p": f"{prefix}%"},
        )
        max_no = 0
        for r in rows:
            val = str(r["vchno"] or "").strip()
            if not val.startswith(prefix):
                continue
            suffix = val[len(prefix):]
            if suffix.isdigit():
                max_no = max(max_no, int(suffix))
        return max_no

    def reserve_voucher(self, tx: Tx, prefix: str, counter_code: str, pad: int = 5) -> str:
        """Port of reserveVoucherWithCounter()."""
        nxt = max(self.gen_int(counter_code), self.last_voucher_number_for_prefix(prefix)) + 1
        self._set_generali(tx, counter_code, nxt)
        return prefix + str(nxt).rjust(pad, "0")

    def preview_voucher(self, prefix: str, counter_code: str, pad: int = 5) -> str:
        nxt = max(self.gen_int(counter_code), self.last_voucher_number_for_prefix(prefix)) + 1
        return prefix + str(nxt).rjust(pad, "0")

    # -- helpers ------------------------------------------------------------
    def account_exists(self, accode: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM accountm WHERE UPPER(TRIM(accode)) = :c LIMIT 1", {"c": accode.strip().upper()}
        ) is not None

    def account_actype2(self, accode: str) -> str:
        v = self.db.scalar("SELECT actype2 FROM accountm WHERE TRIM(accode) = :c LIMIT 1",
                           {"c": accode.strip()})
        return str(v or "").strip().upper()

    def general_profile(self, code: str, default: str = "") -> str:
        if not self.db.table_exists("generals"):
            return default
        v = self.db.scalar("SELECT cvalue FROM generals WHERE code = :c LIMIT 1", {"c": code})
        return default if v is None or str(v).strip() == "" else str(v)

    # -- daybook / daybookpart writers (column-filtered) -------------------
    def insert_daybookpart(self, tx: Tx, row: dict) -> None:
        cols = set(self.db.columns("daybookpart"))
        row = {k: v for k, v in row.items() if k.lower() in cols}
        names = ", ".join(row)
        binds = ", ".join(f":{k}" for k in row)
        tx.execute(f"INSERT INTO daybookpart ({names}) VALUES ({binds})", row)

    def insert_daybook_line(self, tx: Tx, row: dict) -> None:
        cols = set(self.db.columns("daybook"))
        row = {k: v for k, v in row.items() if k.lower() in cols}
        names = ", ".join(row)
        binds = ", ".join(f":{k}" for k in row)
        tx.execute(f"INSERT INTO daybook ({names}) VALUES ({binds})", row)

    def delete_voucher(self, tx: Tx, slno: int) -> None:
        """Remove all rows for a transaction slno (actionDelete)."""
        tx.execute("DELETE FROM daybook WHERE slno = :s", {"s": slno})
        tx.execute("DELETE FROM daybookpart WHERE slno = :s", {"s": slno})
        if self.db.table_exists("pdclist"):
            tx.execute("DELETE FROM pdclist WHERE slno = :s", {"s": slno})
        if self.db.table_exists("daybookratewgt"):
            tx.execute("DELETE FROM daybookratewgt WHERE slno = :s", {"s": slno})

    @staticmethod
    def now_time() -> str:
        return datetime.now().strftime("%H:%M:%S")


def zero_sum(lines: list[dict]) -> Decimal:
    """Sum of daybook line amounts — must be 0 for a balanced transaction."""
    total = Decimal("0")
    for ln in lines:
        total += Decimal(str(ln.get("amount", 0)))
    return total
