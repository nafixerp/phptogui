"""Item Group repository — `itemgrp` table. Source: ItemGroupController.

Schema: itemgrp(code, name, mname, itype, orn, pos, showinstkrep). Delete is
blocked when `items.grpcode` references the group.
"""

from __future__ import annotations

from ...core.db import Database


class ItemGroupRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, t: str = "itemgrp") -> bool:
        return self.db.table_exists(t)

    def has_column(self, t: str, c: str) -> bool:
        return self.db.column_exists(t, c)

    def list(self, search: str = "") -> list[dict]:
        sql = ("SELECT code, name, mname, itype, orn, pos, showinstkrep FROM itemgrp")
        params: dict = {}
        if search:
            params["s"] = f"%{search}%"
            sql += " WHERE code LIKE :s OR name LIKE :s OR mname LIKE :s"
        sql += " ORDER BY name, code LIMIT 500"
        return self.db.fetchall(sql, params)

    def get(self, code: str) -> dict | None:
        return self.db.fetchone(
            "SELECT * FROM itemgrp WHERE UPPER(TRIM(code)) = :c LIMIT 1",
            {"c": code.strip().upper()},
        )

    def exists(self, code: str) -> bool:
        return self.get(code) is not None

    def items_in_group(self, code: str) -> int:
        if not self.db.table_exists("items") or not self.has_column("items", "grpcode"):
            return 0
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM items WHERE UPPER(TRIM(grpcode)) = :c", {"c": code.strip().upper()}
        ) or 0)

    def insert(self, payload: dict) -> None:
        cols = ", ".join(payload)
        binds = ", ".join(f":{k}" for k in payload)
        self.db.execute(f"INSERT INTO itemgrp ({cols}) VALUES ({binds})", payload)

    def update(self, code: str, payload: dict) -> int:
        sets = ", ".join(f"{k} = :{k}" for k in payload)
        params = dict(payload)
        params["_c"] = code.strip().upper()
        res = self.db.execute(f"UPDATE itemgrp SET {sets} WHERE UPPER(TRIM(code)) = :_c", params)
        return getattr(res, "rowcount", 0)

    def delete(self, code: str) -> int:
        res = self.db.execute(
            "DELETE FROM itemgrp WHERE UPPER(TRIM(code)) = :c", {"c": code.strip().upper()}
        )
        return getattr(res, "rowcount", 0)
