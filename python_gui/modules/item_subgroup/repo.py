"""Item Sub-Group repository — `itemsubgrp(code, name)`. Source: ItemSubGroupController.

Delete blocked when `barcode.counter` references the code.
"""

from __future__ import annotations

from ...core.db import Database


class ItemSubGroupRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, t: str = "itemsubgrp") -> bool:
        return self.db.table_exists(t)

    def list(self) -> list[dict]:
        return self.db.fetchall("SELECT code, name FROM itemsubgrp ORDER BY code LIMIT 1000")

    def exists(self, code: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM itemsubgrp WHERE UPPER(TRIM(code)) = :c LIMIT 1", {"c": code.strip().upper()}
        ) is not None

    def upsert(self, code: str, name: str) -> None:
        code_u = code.strip().upper()
        if self.exists(code_u):
            self.db.execute("UPDATE itemsubgrp SET name = :n WHERE UPPER(TRIM(code)) = :c",
                            {"n": name, "c": code_u})
        else:
            self.db.execute("INSERT INTO itemsubgrp (code, name) VALUES (:c, :n)",
                            {"c": code_u, "n": name})

    def used_in_barcode(self, code: str) -> int:
        if not self.db.table_exists("barcode") or not self.db.column_exists("barcode", "counter"):
            return 0
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM barcode WHERE UPPER(TRIM(counter)) = :c", {"c": code.strip().upper()}
        ) or 0)

    def delete(self, code: str) -> int:
        res = self.db.execute("DELETE FROM itemsubgrp WHERE UPPER(TRIM(code)) = :c",
                              {"c": code.strip().upper()})
        return getattr(res, "rowcount", 0)
