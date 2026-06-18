"""Reorder levels — port of ReorderController (get/save/deleteAll).

Per-item min/max reorder bands stored in `rotable` (code, model, size,
weight1, weight2, minqty, maxqty). Saving replaces all rows for the item
(delete-then-insert), skipping bands where both weights are zero, and registers
any new model/size names in `models` (mtype M / S).
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import to_decimal


class ReorderError(Exception):
    pass


class ReorderService:
    def __init__(self, database: Database):
        self.db = database

    def get_item(self, code: str) -> dict | None:
        code = str(code).strip().upper()
        if not self.db.table_exists("items"):
            raise ReorderError("items table not found")
        item = self.db.fetchone(
            "SELECT code, name FROM items WHERE UPPER(TRIM(code)) = :c LIMIT 1", {"c": code})
        if not item:
            return None
        levels = []
        if self.db.table_exists("rotable"):
            levels = self.db.fetchall(
                "SELECT code, model, size, weight1, weight2, minqty, maxqty FROM rotable "
                "WHERE UPPER(TRIM(code)) = :c ORDER BY COALESCE(model,''), COALESCE(size,''), weight1, weight2",
                {"c": code})
        return {"item": item, "levels": levels}

    def save(self, code: str, levels: list[dict]) -> str:
        code = str(code).strip().upper()
        if not code:
            raise ReorderError("Item code required")
        if not self.db.table_exists("rotable"):
            raise ReorderError("rotable table not found")
        has_models = self.db.table_exists("models")
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM rotable WHERE UPPER(TRIM(code)) = :c", {"c": code})
            for lv in levels:
                model = str(lv.get("model") or "").strip().upper()
                size = str(lv.get("size") or "").strip().upper()
                w1 = to_decimal(lv.get("weight1"))
                w2 = to_decimal(lv.get("weight2"))
                if w1 == 0 and w2 == 0:
                    continue
                tx.execute(
                    "INSERT INTO rotable (code, model, size, weight1, weight2, minqty, maxqty) "
                    "VALUES (:code, :model, :size, :w1, :w2, :minq, :maxq)",
                    {"code": code, "model": model or None, "size": size or None,
                     "w1": w1, "w2": w2, "minq": int(lv.get("minqty") or 0),
                     "maxq": int(lv.get("maxqty") or 0)})
                if has_models and model:
                    self._register_model(tx, "M", model)
                if has_models and size:
                    self._register_model(tx, "S", size)
        return "Updated successfully"

    def delete_all(self, code: str) -> str:
        code = str(code).strip().upper()
        if self.db.table_exists("rotable"):
            self.db.execute("DELETE FROM rotable WHERE UPPER(TRIM(code)) = :c", {"c": code})
        return "All reorder levels deleted"

    def _register_model(self, tx, mtype: str, name: str) -> None:
        exists = tx.fetchall(
            "SELECT 1 FROM models WHERE mtype = :t AND name = :n LIMIT 1",
            {"t": mtype, "n": name})
        if not exists:
            tx.execute("INSERT INTO models (mtype, name) VALUES (:t, :n)", {"t": mtype, "n": name})
