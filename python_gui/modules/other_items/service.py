"""Other Items master — port of OtherItemsController (add/edit/delete/list).

A simple non-jewellery item master in `itemsothers` (code/name/group, sale &
purchase rate, cost, opening + current stock). Codes are upper-cased and unique.
All writes are column-filtered to the live schema.
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import money

_FIELDS = ["name", "grp", "srate", "prate", "cost", "opcost", "opstock", "stock", "keepstk"]


class OtherItemsError(Exception):
    pass


class OtherItemsService:
    def __init__(self, database: Database):
        self.db = database

    def list(self, q: str = "") -> list[dict]:
        if not self.db.table_exists("itemsothers"):
            return []
        where = ["1=1"]
        params: dict = {}
        if q.strip():
            where.append("(UPPER(code) LIKE :q OR UPPER(name) LIKE :q)")
            params["q"] = f"%{q.strip().upper()}%"
        return self.db.fetchall(
            f"SELECT * FROM itemsothers WHERE {' AND '.join(where)} ORDER BY code LIMIT 5000", params)

    def exists(self, code: str) -> bool:
        if not self.db.table_exists("itemsothers"):
            return False
        return bool(self.db.fetchone(
            "SELECT 1 FROM itemsothers WHERE UPPER(TRIM(code)) = :c LIMIT 1",
            {"c": str(code).strip().upper()}))

    def _payload(self, data: dict) -> dict:
        cols = set(self.db.columns("itemsothers"))
        row = {
            "name": str(data.get("name") or "").strip().upper(),
            "grp": str(data.get("grp") or "").strip(),
            "srate": money(data.get("srate")), "prate": money(data.get("prate")),
            "cost": money(data.get("cost")), "opcost": money(data.get("opcost")),
            "opstock": int(data.get("opstock") or 0), "stock": int(data.get("stock") or 0),
            "keepstk": int(data.get("keepstk") if data.get("keepstk") not in (None, "") else 1),
        }
        return {k: v for k, v in row.items() if k in cols}

    def add(self, data: dict) -> str:
        if not self.db.table_exists("itemsothers"):
            raise OtherItemsError("`itemsothers` table not found.")
        code = str(data.get("code") or "").strip().upper()
        if not code:
            raise OtherItemsError("Item code is empty.")
        if self.exists(code):
            raise OtherItemsError("This item already exists.")
        payload = {"code": code, **self._payload(data)}
        names = ", ".join(payload); binds = ", ".join(f":{k}" for k in payload)
        self.db.execute(f"INSERT INTO itemsothers ({names}) VALUES ({binds})", payload)
        return "Item added successfully."

    def edit(self, data: dict) -> str:
        if not self.db.table_exists("itemsothers"):
            raise OtherItemsError("`itemsothers` table not found.")
        code = str(data.get("code") or "").strip().upper()
        if not code:
            raise OtherItemsError("Item code is empty.")
        payload = self._payload(data)
        if not payload:
            return "Item updated successfully."
        sets = ", ".join(f"{k} = :{k}" for k in payload)
        self.db.execute(f"UPDATE itemsothers SET {sets} WHERE UPPER(TRIM(code)) = :c",
                        {**payload, "c": code})
        return "Item updated successfully."

    def delete(self, code: str) -> str:
        if not self.db.table_exists("itemsothers"):
            raise OtherItemsError("`itemsothers` table not found.")
        self.db.execute("DELETE FROM itemsothers WHERE UPPER(TRIM(code)) = :c",
                        {"c": str(code).strip().upper()})
        return "Item deleted."
