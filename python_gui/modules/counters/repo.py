"""Counters repository — `counter(code, name, startbillno)`. Source: CountersController.

On save, when startbillno>0 and the counter has no sales yet, the `generali`
bill-number counter is seeded. Delete blocked when used in `barcode`.
"""

from __future__ import annotations

from ...core.db import Database


class CountersRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, t: str = "counter") -> bool:
        return self.db.table_exists(t)

    def list(self) -> list[dict]:
        return self.db.fetchall("SELECT code, name, startbillno FROM counter ORDER BY code")

    def exists(self, code: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM counter WHERE code = :c LIMIT 1", {"c": code.strip().upper()}
        ) is not None

    def upsert(self, tx, code: str, name: str, startbillno) -> None:
        if tx.scalar("SELECT 1 FROM counter WHERE code = :c LIMIT 1", {"c": code}) is not None:
            tx.execute("UPDATE counter SET name = :n, startbillno = :s WHERE code = :c",
                       {"n": name, "s": startbillno, "c": code})
        else:
            tx.execute("INSERT INTO counter (code, name, startbillno) VALUES (:c, :n, :s)",
                       {"c": code, "n": name, "s": startbillno})

    def sales_count(self, code: str) -> int:
        if not self.db.table_exists("salesm"):
            return -1  # signal "cannot check" (matches: only seed when salesm exists)
        return int(self.db.scalar(
            "SELECT COUNT(slno) FROM salesm WHERE counter = :c", {"c": code}
        ) or 0)

    def seed_generali(self, tx, code: str, value) -> None:
        if tx.scalar("SELECT 1 FROM generali WHERE code = :c LIMIT 1", {"c": code}) is not None:
            tx.execute("UPDATE generali SET cvalue = :v WHERE code = :c", {"v": value, "c": code})
        else:
            tx.execute("INSERT INTO generali (code, cvalue) VALUES (:c, :v)", {"c": code, "v": value})

    def has_generali(self) -> bool:
        return self.db.table_exists("generali")

    def used_in_barcode(self, code: str) -> bool:
        if not self.db.table_exists("barcode"):
            return False
        return self.db.fetchone(
            "SELECT 1 FROM barcode WHERE counter = :c LIMIT 1", {"c": code.strip().upper()}
        ) is not None

    def delete(self, code: str) -> None:
        self.db.execute("DELETE FROM counter WHERE code = :c", {"c": code.strip().upper()})
