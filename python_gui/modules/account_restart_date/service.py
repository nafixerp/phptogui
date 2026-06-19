"""Account Restart Date — port of AccountRestartDateController.

Sets an account's opening/restart date (``accountm.opdate``) by code. Used to
re-base an account's running balance from a given date.
"""

from __future__ import annotations

from ...core.db import Database


class AccountRestartDateError(Exception):
    pass


class AccountRestartDateService:
    def __init__(self, database: Database):
        self.db = database

    def load(self, code: str) -> dict | None:
        if not self.db.table_exists("accountm"):
            return None
        row = self.db.fetchone(
            "SELECT TRIM(COALESCE(name,'')) AS name, opdate FROM accountm "
            "WHERE UPPER(TRIM(accode)) = :c LIMIT 1", {"c": str(code).strip().upper()})
        if not row:
            return None
        opdate = row.get("opdate")
        if opdate == "0000-00-00":
            opdate = None
        return {"name": str(row.get("name") or "").strip(), "opdate": opdate}

    def search(self, q: str) -> list[dict]:
        if not self.db.table_exists("accountm") or not q.strip():
            return []
        like = f"{q.strip()}%"; likeany = f"%{q.strip()}%"
        return self.db.fetchall(
            "SELECT TRIM(accode) AS code, TRIM(COALESCE(name,'')) AS name FROM accountm "
            "WHERE accode LIKE :a OR name LIKE :b ORDER BY accode LIMIT 30",
            {"a": like, "b": likeany})

    def save(self, code: str, opdate: str) -> str:
        code = str(code).strip().upper()
        opdate = str(opdate).strip()
        if not code:
            raise AccountRestartDateError("Account required")
        if not opdate:
            raise AccountRestartDateError("Restart date required")
        if not self.db.table_exists("accountm"):
            raise AccountRestartDateError("accountm table not found")
        res = self.db.execute(
            "UPDATE accountm SET opdate = :d WHERE UPPER(TRIM(accode)) = :c",
            {"d": opdate, "c": code})
        if getattr(res, "rowcount", 0) == 0:
            raise AccountRestartDateError("Account not found or no change")
        return "Updated"
