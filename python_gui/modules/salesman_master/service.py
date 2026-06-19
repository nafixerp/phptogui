"""Salesman Master — port of ``AccountMasterController::apiSalesMan``.

Grid CRUD over the ``sman`` table (``code``/``name``/``accode``/``active``).
``save_all`` mirrors the controller's full-table replace (delete-all then
re-insert) with each non-blank ``accode`` validated against ``accountm``; codes
upper-cased, names upper-cased, ``active`` normalised to Y/N. A salesman that is
referenced by ``orderm.smcode`` cannot be removed (usage guard).
"""

from __future__ import annotations

from ...core.auth import AppSession
from ...core.db import Database

_REQUIRED = ("code", "name", "accode", "active")


class SalesmanError(Exception):
    pass


class SalesmanMasterService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def _check_table(self) -> None:
        if not self.db.table_exists("sman"):
            raise SalesmanError("Table sman not found")
        for col in _REQUIRED:
            if not self.db.column_exists("sman", col):
                raise SalesmanError("Table sman must contain code, name, accode, active columns")

    def list(self) -> list[dict]:
        if not self.db.table_exists("sman"):
            return []
        return self.db.fetchall(
            "SELECT TRIM(code) AS code, TRIM(name) AS name, TRIM(accode) AS accode, "
            "COALESCE(active,'Y') AS active FROM sman ORDER BY code")

    def account_list(self) -> list[dict]:
        if not self.db.table_exists("accountm"):
            return []
        name_col = "acname" if self.db.column_exists("accountm", "acname") else "name"
        removed = " AND (removed <> 1 OR removed IS NULL)" if self.db.column_exists("accountm", "removed") else ""
        return self.db.fetchall(
            f"SELECT TRIM(accode) AS code, COALESCE(TRIM({name_col}),'') AS name FROM accountm "
            f"WHERE TRIM(accode) <> ''{removed} ORDER BY {name_col} ASC")

    def usage_count(self, code: str) -> int:
        code = str(code or "").strip().upper()
        if not code or not self.db.column_exists("orderm", "smcode"):
            return 0
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM orderm WHERE TRIM(smcode) = :c", {"c": code}) or 0)

    def check_usage(self, code: str) -> dict:
        n = self.usage_count(code)
        return {"count": n, "in_use": n > 0}

    def save_all(self, rows: list[dict]) -> str:
        """Full-table replace (faithful to the controller's save action)."""
        self._check_table()
        clean: list[dict] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip().upper()
            if not code:
                continue
            active = str(row.get("active") or "Y").strip().upper()
            clean.append({
                "code": code,
                "name": str(row.get("name") or "").strip().upper(),
                "accode": str(row.get("accode") or "").strip().upper(),
                "active": active if active == "N" else "Y",
            })
        with self.db.transaction() as tx:
            for r in clean:
                if r["accode"] and not tx.fetchall(
                        "SELECT 1 FROM accountm WHERE TRIM(accode) = :a LIMIT 1", {"a": r["accode"]}):
                    raise SalesmanError(f"Invalid account code: {r['accode']}")
            tx.execute("DELETE FROM sman")
            for r in clean:
                tx.execute("INSERT INTO sman (code, name, accode, active) "
                           "VALUES (:code, :name, :accode, :active)", r)
        return "Data saved successfully"

    def delete(self, code: str) -> str:
        """Remove one salesman after the orderm usage guard."""
        self._check_table()
        code = str(code or "").strip().upper()
        if not code:
            raise SalesmanError("Code is required")
        if self.usage_count(code) > 0:
            raise SalesmanError("You can't delete this entry - it is being used in orders")
        self.db.execute("DELETE FROM sman WHERE TRIM(code) = :c", {"c": code})
        return "Deleted."
