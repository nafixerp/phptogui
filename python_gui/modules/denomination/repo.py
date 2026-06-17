"""Denomination Master repository — `denom_master(code, name, cvalue)`.

Source: DenominationMasterController (retrieve/save). Save deletes listed codes
then upserts rows; the desktop edits per row.
"""

from __future__ import annotations

from ...core.db import Database


class DenominationRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, t: str = "denom_master") -> bool:
        return self.db.table_exists(t)

    def list(self) -> list[dict]:
        return self.db.fetchall("SELECT code, name, cvalue FROM denom_master ORDER BY code")

    def exists(self, code: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM denom_master WHERE code = :c LIMIT 1", {"c": code.strip().upper()}
        ) is not None

    def upsert(self, code: str, name: str, cvalue) -> None:
        code_u = code.strip().upper()
        if self.exists(code_u):
            self.db.execute("UPDATE denom_master SET name = :n, cvalue = :v WHERE code = :c",
                            {"n": name, "v": cvalue, "c": code_u})
        else:
            self.db.execute("INSERT INTO denom_master (code, name, cvalue) VALUES (:c, :n, :v)",
                            {"c": code_u, "n": name, "v": cvalue})

    def delete(self, code: str) -> None:
        self.db.execute("DELETE FROM denom_master WHERE code = :c", {"c": code.strip().upper()})
