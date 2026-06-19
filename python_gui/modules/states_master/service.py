"""States Master — port of ``NativeStatesController``.

Grid CRUD over whichever state table exists (``state`` / ``state_master`` /
``statestate``), resolving the key/name columns dynamically. ``save_all`` upserts
by code (update name if present, else insert); a state referenced by a sales
record (``salesm.statecode``/``state``/``scode``) cannot be deleted.
"""

from __future__ import annotations

from ...core.auth import AppSession
from ...core.db import Database


class StatesError(Exception):
    pass


class StatesMasterService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def _cols(self, table: str) -> set[str]:
        try:
            return {c.lower() for c in self.db.columns(table)} if self.db.table_exists(table) else set()
        except Exception:
            return set()

    def resolve_meta(self) -> dict | None:
        """Pick (table, key_col, name_col) from the first matching state table."""
        cols = self._cols("state")
        if cols:
            key = "code" if "code" in cols else ("state" if "state" in cols else None)
            name = "name" if "name" in cols else ("state" if "state" in cols else None)
            if key and name:
                return {"table": "state", "key": key, "name": name}
        cols = self._cols("state_master")
        if "code" in cols and "name" in cols:
            return {"table": "state_master", "key": "code", "name": "name"}
        cols = self._cols("statestate")
        if cols:
            key = "code" if "code" in cols else ("state" if "state" in cols else None)
            name = "name" if "name" in cols else ("state" if "state" in cols else None)
            if key and name:
                return {"table": "statestate", "key": key, "name": name}
        return None

    def list(self) -> list[dict]:
        meta = self.resolve_meta()
        if not meta:
            return []
        return self.db.fetchall(
            f"SELECT {meta['key']} AS code, {meta['name']} AS name FROM {meta['table']} "
            f"ORDER BY {meta['key']}")

    def usage_count(self, code: str) -> int:
        code = str(code or "").strip().upper()
        if not code or not self.db.table_exists("salesm"):
            return 0
        cols = self._cols("salesm")
        for candidate in ("statecode", "state", "scode"):
            if candidate in cols:
                return int(self.db.scalar(
                    f"SELECT COUNT(*) FROM salesm WHERE {candidate} = :c", {"c": code}) or 0)
        return 0

    def check_usage(self, code: str) -> dict:
        n = self.usage_count(code)
        return {"count": n, "in_use": n > 0}

    def save_all(self, rows: list[dict]) -> dict:
        meta = self.resolve_meta()
        if not meta:
            raise StatesError("State table not found")
        inserted = updated = 0
        key, name, table = meta["key"], meta["name"], meta["table"]
        with self.db.transaction() as tx:
            for row in rows or []:
                code = str(row.get("code") or "").strip().upper()
                nm = str(row.get("name") or "").strip()
                if not code or not nm:
                    continue
                if tx.fetchall(f"SELECT 1 FROM {table} WHERE {key} = :c LIMIT 1", {"c": code}):
                    if name != key:
                        tx.execute(f"UPDATE {table} SET {name} = :n WHERE {key} = :c", {"n": nm, "c": code})
                    updated += 1
                else:
                    if name != key:
                        tx.execute(f"INSERT INTO {table} ({key}, {name}) VALUES (:c, :n)", {"c": code, "n": nm})
                    else:
                        tx.execute(f"INSERT INTO {table} ({key}) VALUES (:c)", {"c": code})
                    inserted += 1
        return {"inserted": inserted, "updated": updated,
                "message": f"Data saved successfully. {inserted} inserted, {updated} updated."}

    def delete(self, code: str) -> str:
        meta = self.resolve_meta()
        if not meta:
            raise StatesError("State table not found")
        code = str(code or "").strip().upper()
        if not code:
            raise StatesError("State code is required")
        n = self.usage_count(code)
        if n > 0:
            raise StatesError(f"Cannot delete this state. It is referenced in {n} sales record(s).")
        res = self.db.execute(
            f"DELETE FROM {meta['table']} WHERE {meta['key']} = :c", {"c": code})
        if getattr(res, "rowcount", 0) < 1:
            raise StatesError("State not found")
        return "State deleted successfully"
