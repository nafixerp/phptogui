"""Hallmark records — `hallmark_records`. Source: HallmarkController.

CRUD over the BIS hallmark register. NOTE: hallmark_records is an
application-created (non-legacy) table; this module guards on its presence and
no-ops gracefully if absent on the frozen schema.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import to_decimal

_FIELDS = ["batch_no", "item_code", "barcode", "huid", "bis_centre", "purity_grade",
           "purity_name", "certificate_no", "hallmark_date", "article_desc", "notes"]


class HallmarkService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def available(self) -> bool:
        return self.db.table_exists("hallmark_records")

    def list(self, search: str = "") -> list[dict]:
        if not self.available():
            return []
        sql = "SELECT id, batch_no, item_code, huid, purity_name, weight, hallmark_date FROM hallmark_records"
        params: dict = {}
        if search.strip():
            params["s"] = f"%{search.strip()}%"
            sql += " WHERE batch_no LIKE :s OR item_code LIKE :s OR huid LIKE :s OR barcode LIKE :s"
        sql += " ORDER BY id DESC LIMIT 500"
        return self.db.fetchall(sql, params)

    def save(self, data: dict) -> str:
        if not self.available():
            raise RuntimeError("hallmark_records table not found")
        rid = int(to_decimal(data.get("id", 0)) or 0)
        row = {f: (str(data.get(f) or "").strip() or (None if f == "huid" else "")) for f in _FIELDS}
        if not row.get("hallmark_date"):
            row["hallmark_date"] = date.today().isoformat()
        row["weight"] = to_decimal(data.get("weight", 0)) or Decimal("0")
        with self.db.transaction() as tx:
            if rid > 0:
                sets = ", ".join(f"{k} = :{k}" for k in row)
                params = dict(row); params["_id"] = rid
                tx.execute(f"UPDATE hallmark_records SET {sets} WHERE id = :_id", params)
            else:
                cols = ", ".join(row); binds = ", ".join(f":{k}" for k in row)
                tx.execute(f"INSERT INTO hallmark_records ({cols}) VALUES ({binds})", row)
        return "Hallmark record saved"

    def delete(self, rid: int) -> str:
        if not self.available():
            raise RuntimeError("hallmark_records table not found")
        self.db.execute("DELETE FROM hallmark_records WHERE id = :id", {"id": int(to_decimal(rid) or 0)})
        return "Deleted"
