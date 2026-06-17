"""Stock Type repository — SQL against the frozen `stktype` table.

Schema (complete_database_export.sql:2514): stktype(code CHAR(5) PK,
name VARCHAR(20), def SMALLINT, compare SMALLINT). NOTE: the production `demo`
dump has NO `id` column (code is the PK); the Eloquent model
(app/Models/StockType.php) uses `id` in setAsDefault(), which would error on
this schema. We therefore key the single-default invariant on `code`, which is
correct for both the legacy schema and the migration schema. See service.py.

Usage / delete logic ported from StockType::isInUse() and deleteWithItems().
"""

from __future__ import annotations

from ...core.db import Database

# Tables (besides itemsstk) checked for `stktype` usage in StockType::isInUse().
_USAGE_TABLES = ["salesd", "salesrd", "purchased", "purchaserd", "smithd", "refineryd", "repaird"]


class StockTypeRepo:
    def __init__(self, database: Database):
        self.db = database

    def table_exists(self) -> bool:
        return self.db.table_exists("stktype")

    def list(self) -> list[dict]:
        # StockType::orderBy('code')->get()
        return self.db.fetchall("SELECT code, name, def, compare FROM stktype ORDER BY code")

    def get_by_code(self, code: str) -> dict | None:
        return self.db.fetchone(
            "SELECT code, name, def, compare FROM stktype WHERE code = :c LIMIT 1",
            {"c": code.strip().upper()},
        )

    def code_exists(self, code: str) -> bool:
        return self.get_by_code(code) is not None

    def get_default(self) -> dict | None:
        return self.db.fetchone(
            "SELECT code, name, def, compare FROM stktype WHERE def = 1 LIMIT 1"
        )

    @staticmethod
    def _set_default_in_tx(tx, code: str) -> None:
        # Single-default invariant, keyed on `code` (StockType::setAsDefault intent).
        tx.execute("UPDATE stktype SET def = 0 WHERE code <> :code", {"code": code})
        tx.execute("UPDATE stktype SET def = 1 WHERE code = :code", {"code": code})

    def create(self, code: str, name: str, def_: int, compare: int, make_default: bool) -> None:
        """INSERT + optional setAsDefault, atomically (StockTypeController::store)."""
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO stktype (code, name, def, compare) VALUES (:code, :name, :def, :compare)",
                {"code": code, "name": name, "def": def_, "compare": compare},
            )
            if make_default:
                self._set_default_in_tx(tx, code)

    def save(self, code: str, name: str, def_: int, compare: int, make_default: bool) -> None:
        """UPDATE + optional setAsDefault, atomically (StockTypeController::update)."""
        with self.db.transaction() as tx:
            tx.execute(
                "UPDATE stktype SET name = :name, def = :def, compare = :compare WHERE code = :code",
                {"code": code, "name": name, "def": def_, "compare": compare},
            )
            if make_default:
                self._set_default_in_tx(tx, code)

    # -- usage / delete -----------------------------------------------------
    def usage(self, code: str) -> dict:
        """Port of StockType::isInUse() — column-guarded counts across tables."""
        code = code.strip().upper()
        counts = {t: 0 for t in (["itemsstk"] + _USAGE_TABLES + ["itemadj"])}

        if self.db.table_exists("itemsstk") and self.db.column_exists("itemsstk", "stktype"):
            nonzero_cols = [c for c in ("qty", "qtyb", "weight", "weightb")
                            if self.db.column_exists("itemsstk", c)]
            sql = "SELECT COUNT(*) FROM itemsstk WHERE stktype = :c"
            if nonzero_cols:
                ors = " OR ".join(f"{c} <> 0" for c in nonzero_cols)
                sql += f" AND ({ors})"
            counts["itemsstk"] = int(self.db.scalar(sql, {"c": code}) or 0)

        for tbl in _USAGE_TABLES:
            if self.db.table_exists(tbl) and self.db.column_exists(tbl, "stktype"):
                counts[tbl] = int(
                    self.db.scalar(f"SELECT COUNT(*) FROM {tbl} WHERE stktype = :c", {"c": code}) or 0
                )

        if self.db.table_exists("itemadj"):
            has_from = self.db.column_exists("itemadj", "fromstktype")
            has_to = self.db.column_exists("itemadj", "tostktype")
            ors = []
            if has_from:
                ors.append("fromstktype = :c")
            if has_to:
                ors.append("tostktype = :c")
            if ors:
                counts["itemadj"] = int(
                    self.db.scalar(
                        f"SELECT COUNT(*) FROM itemadj WHERE {' OR '.join(ors)}", {"c": code}
                    ) or 0
                )

        counts["total"] = sum(counts.values())
        counts["itemsonly"] = counts["itemsstk"]
        return counts

    def delete_with_items(self, code: str) -> None:
        """Port of StockType::deleteWithItems() — atomic delete of items + the row."""
        code = code.strip().upper()
        delete_items = (
            self.db.table_exists("itemsstk") and self.db.column_exists("itemsstk", "stktype")
        )
        with self.db.transaction() as tx:
            if delete_items:
                tx.execute("DELETE FROM itemsstk WHERE stktype = :c", {"c": code})
            tx.execute("DELETE FROM stktype WHERE code = :c", {"c": code})
