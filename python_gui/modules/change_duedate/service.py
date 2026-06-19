"""Change Due-date — port of ChangeDuedateController.

Updates a party's ``clients.duedate`` by code. Returns whether a row changed.
"""

from __future__ import annotations

from ...core.db import Database


class ChangeDuedateError(Exception):
    pass


class ChangeDuedateService:
    def __init__(self, database: Database):
        self.db = database

    def party(self, code: str) -> dict | None:
        if not self.db.table_exists("clients"):
            return None
        return self.db.fetchone(
            "SELECT TRIM(code) AS code, TRIM(COALESCE(name,'')) AS name, duedate "
            "FROM clients WHERE UPPER(TRIM(code)) = :c LIMIT 1",
            {"c": str(code).strip().upper()})

    def save(self, code: str, duedate: str) -> str:
        code = str(code).strip().upper()
        duedate = str(duedate).strip()
        if not code:
            raise ChangeDuedateError("Party required")
        if not duedate:
            raise ChangeDuedateError("New duedate required")
        if not self.db.table_exists("clients"):
            raise ChangeDuedateError("clients table not found")
        res = self.db.execute(
            "UPDATE clients SET duedate = :d WHERE UPPER(TRIM(code)) = :c",
            {"d": duedate, "c": code})
        if getattr(res, "rowcount", 0) == 0:
            raise ChangeDuedateError("Party not found or no change")
        return "Updated"
