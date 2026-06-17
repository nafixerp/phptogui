"""Purity Type repository — `itemsqtype(code, touch)`. Source: ItemPurityTypeController.

Rename cascades the code across related tables; delete/usage scans the same set.
"""

from __future__ import annotations

from ...core.db import Database

# table -> column referencing a purity code (updateRelatedTables / checkCodeUsage)
_RELATED = {
    "items": "defquality", "salesd": "iqtype", "purchased": "iqtype",
    "salesrd": "iqtype", "mctable": "iqtype", "barcode": "qtype",
    "orderd": "iqtype", "orderdga": "iqtype", "wstgtable": "iqtype",
}


class PurityTypeRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, t: str = "itemsqtype") -> bool:
        return self.db.table_exists(t)

    def list(self) -> list[dict]:
        return self.db.fetchall("SELECT code, touch FROM itemsqtype ORDER BY code")

    def exists(self, code: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM itemsqtype WHERE UPPER(TRIM(code)) = :c LIMIT 1", {"c": code.strip().upper()}
        ) is not None

    def get(self, code: str) -> dict | None:
        return self.db.fetchone(
            "SELECT code, touch FROM itemsqtype WHERE UPPER(TRIM(code)) = :c LIMIT 1",
            {"c": code.strip().upper()},
        )

    def insert(self, tx, code: str, touch) -> None:
        tx.execute("INSERT INTO itemsqtype (code, touch) VALUES (:c, :t)",
                   {"c": code.strip().upper(), "t": touch})

    def update(self, tx, original: str, code: str, touch) -> None:
        tx.execute("UPDATE itemsqtype SET code = :nc, touch = :t WHERE UPPER(TRIM(code)) = :oc",
                   {"nc": code.strip().upper(), "t": touch, "oc": original.strip().upper()})

    def update_touch(self, tx, code: str, touch) -> None:
        tx.execute("UPDATE itemsqtype SET touch = :t WHERE UPPER(TRIM(code)) = :c",
                   {"t": touch, "c": code.strip().upper()})

    def delete(self, tx, code: str) -> None:
        tx.execute("DELETE FROM itemsqtype WHERE UPPER(TRIM(code)) = :c", {"c": code.strip().upper()})

    def usage_count(self, code: str) -> int:
        total = 0
        code_u = code.strip().upper()
        for table, field in _RELATED.items():
            if self.db.table_exists(table) and self.db.column_exists(table, field):
                total += int(self.db.scalar(
                    f"SELECT COUNT(*) FROM {table} WHERE UPPER(TRIM({field})) = :c", {"c": code_u}
                ) or 0)
        return total

    def cascade_rename(self, tx, old: str, new: str) -> None:
        old_u, new_u = old.strip().upper(), new.strip().upper()
        for table, field in _RELATED.items():
            if self.db.table_exists(table) and self.db.column_exists(table, field):
                tx.execute(f"UPDATE {table} SET {field} = :n WHERE UPPER(TRIM({field})) = :o",
                           {"n": new_u, "o": old_u})
