"""Item Master repository — `items` table. Source: ItemMasterController.

The controller builds a payload then filters it to the columns that actually
exist in `items` (column-driven). Delete is blocked for reserved items and items
with non-zero transaction weight; rename cascades the code across many tables.
"""

from __future__ import annotations

from ...core.db import Database, Tx

# (table, weight-column) summed by canDeleteItem(); item must net to ~0.
_DELETE_WEIGHT_TABLES = [
    ("salesd", "weight"), ("salesrd", "weight"), ("purchased", "weight"),
    ("purchaserd", "weight"), ("orderd", "weight"), ("repaird", "weight"),
    ("smithd", "weight"), ("refineryd", "issuedwgt"), ("refineryd", "rcvdwgt"),
]

# table -> code columns to cascade on rename (itemRenameReferences()).
_RENAME_REFS = {
    "itemadj": ["fromcode", "tocode"], "itemsstk": ["code"], "orderd": ["code"],
    "orderdmodel": ["code"], "orderdga": ["code"], "salesd": ["code"],
    "salesrd": ["code"], "purchased": ["code"], "purchaserd": ["code"],
    "refineryd": ["code"], "repaird": ["code"], "smithd": ["code"],
    "smithnewwrk": ["code"], "smithsusp": ["code"], "wstgtable": ["code"],
    "mctable": ["code"], "barcode": ["icode"], "itemadjverify": ["code"],
    "itemstmp": ["code"], "modelm": ["icode"],
}


class ItemMasterRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, t: str = "items") -> bool:
        return self.db.table_exists(t)

    def has_column(self, t: str, c: str) -> bool:
        return self.db.column_exists(t, c)

    def columns(self, t: str = "items") -> set[str]:
        return set(self.db.columns(t))

    def filter_columns(self, row: dict, t: str = "items") -> dict:
        cols = self.columns(t)
        return {k: v for k, v in row.items() if k.lower() in cols}

    def exists(self, code: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM items WHERE UPPER(TRIM(code)) = :c LIMIT 1", {"c": code.strip().upper()}
        ) is not None

    def get(self, code: str) -> dict | None:
        return self.db.fetchone(
            "SELECT * FROM items WHERE UPPER(TRIM(code)) = :c LIMIT 1", {"c": code.strip().upper()}
        )

    def search(self, term: str, limit: int = 200) -> list[dict]:
        sql = "SELECT TRIM(code) AS code, TRIM(name) AS name, itype, grpcode FROM items"
        params: dict = {}
        if term:
            params["s"] = f"%{term}%"
            sql += " WHERE TRIM(code) LIKE :s OR TRIM(name) LIKE :s"
        sql += " ORDER BY code LIMIT :lim"
        params["lim"] = limit
        return self.db.fetchall(sql, params)

    def insert(self, tx: Tx, payload: dict) -> None:
        cols = ", ".join(payload)
        binds = ", ".join(f":{k}" for k in payload)
        tx.execute(f"INSERT INTO items ({cols}) VALUES ({binds})", payload)

    def update(self, tx: Tx, code: str, payload: dict) -> None:
        sets = ", ".join(f"{k} = :{k}" for k in payload)
        params = dict(payload)
        params["_c"] = code.strip().upper()
        tx.execute(f"UPDATE items SET {sets} WHERE UPPER(TRIM(code)) = :_c", params)

    def delete(self, code: str) -> None:
        self.db.execute("DELETE FROM items WHERE UPPER(TRIM(code)) = :c", {"c": code.strip().upper()})

    def transaction_weight(self, code: str) -> float:
        """SUM of transaction weights for the item (canDeleteItem)."""
        code_u = code.strip().upper()
        total = 0.0
        for table, col in _DELETE_WEIGHT_TABLES:
            if self.has_table(table) and self.has_column(table, col) and self.has_column(table, "code"):
                total += float(self.db.scalar(
                    f"SELECT COALESCE(SUM({col}), 0) FROM {table} WHERE UPPER(TRIM(code)) = :c", {"c": code_u}
                ) or 0)
        if self.has_table("itemadj"):
            if self.has_column("itemadj", "fromcode") and self.has_column("itemadj", "fromwgt"):
                total += float(self.db.scalar(
                    "SELECT COALESCE(SUM(fromwgt),0) FROM itemadj WHERE UPPER(TRIM(fromcode)) = :c", {"c": code_u}
                ) or 0)
            if self.has_column("itemadj", "tocode") and self.has_column("itemadj", "towgt"):
                total += float(self.db.scalar(
                    "SELECT COALESCE(SUM(towgt),0) FROM itemadj WHERE UPPER(TRIM(tocode)) = :c", {"c": code_u}
                ) or 0)
        return total

    # -- option lookups -----------------------------------------------------
    def options(self) -> dict:
        def lk(table, code_c, name_c):
            if not self.has_table(table):
                return []
            return self.db.fetchall(
                f"SELECT TRIM({code_c}) AS code, TRIM({name_c}) AS name FROM {table} ORDER BY {code_c}"
            )
        return {
            "groups": lk("itemgrp", "code", "name"),
            "subgroups": lk("itemsubgrp", "code", "name"),
            "stocktypes": lk("stktype", "code", "name"),
            "qualities": (self.db.fetchall("SELECT TRIM(code) AS code, touch FROM itemsqtype ORDER BY code")
                          if self.has_table("itemsqtype") else []),
            "billtypes": lk("salestype", "code", "name"),
        }

    def rename(self, old: str, new: str, merge_existing: bool) -> dict:
        old_u, new_u = old.strip().upper(), new.strip().upper()
        counts: dict = {}
        with self.db.transaction() as tx:
            if not (tx.scalar("SELECT 1 FROM items WHERE UPPER(TRIM(code)) = :c LIMIT 1", {"c": old_u})):
                return {"success": False, "message": "Invalid old item code"}
            new_exists = tx.scalar("SELECT 1 FROM items WHERE UPPER(TRIM(code)) = :c LIMIT 1", {"c": new_u}) is not None
            if new_exists and not merge_existing:
                return {"success": False, "message": "New item code already exists", "exists": True}
            if new_exists:
                tx.execute("DELETE FROM items WHERE UPPER(TRIM(code)) = :c", {"c": old_u})
            else:
                tx.execute("UPDATE items SET code = :n WHERE UPPER(TRIM(code)) = :o", {"n": new_u, "o": old_u})
            for table, cols in _RENAME_REFS.items():
                if not self.has_table(table):
                    continue
                for col in cols:
                    if self.has_column(table, col):
                        tx.execute(f"UPDATE {table} SET {col} = :n WHERE UPPER(TRIM({col})) = :o",
                                   {"n": new_u, "o": old_u})
        return {"success": True, "message": "Item renamed successfully", "merged": new_exists}
