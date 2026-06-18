"""Party Opening Weight — updates `accountm.opwgt` / `opwgtb`.

Source: PartyOpWeightController. Sets the opening weight balance on an existing
account (rounded to 3 dp). opwgtb updated only when the column exists.
"""

from __future__ import annotations

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import weight


class PartyOpWeightError(Exception):
    pass


class PartyOpWeightService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def list_accounts(self, search: str = "") -> list[dict]:
        if not self.db.table_exists("accountm"):
            return []
        sql = "SELECT TRIM(accode) AS accode, TRIM(name) AS name, COALESCE(opwgt,0) AS opwgt FROM accountm WHERE 1=1"
        params: dict = {}
        if search.strip():
            params["s"] = f"%{search.strip()}%"
            sql += " AND (TRIM(accode) LIKE :s OR TRIM(name) LIKE :s)"
        sql += " ORDER BY accode LIMIT 300"
        return self.db.fetchall(sql, params)

    def save(self, code: str, opwgt, opwgtb=0) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise PartyOpWeightError("Party code is required")
        if not self.db.table_exists("accountm"):
            raise PartyOpWeightError("accountm table not found")
        if not self.db.fetchone("SELECT 1 FROM accountm WHERE TRIM(accode) = :c LIMIT 1", {"c": code}):
            raise PartyOpWeightError("Account not found")
        updates = {"opwgt": weight(opwgt)}
        if self.db.column_exists("accountm", "opwgtb"):
            updates["opwgtb"] = weight(opwgtb)
        sets = ", ".join(f"{k} = :{k}" for k in updates)
        params = dict(updates); params["_c"] = code
        self.db.execute(f"UPDATE accountm SET {sets} WHERE TRIM(accode) = :_c", params)
        return f"Op. Weight saved for {code}"
