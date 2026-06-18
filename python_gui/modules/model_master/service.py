"""Model Master — `models(mtype, name)`. Source: ModelMasterController +
ProductModel::bulkUpdateByType. Bulk-replace all names for a model type
('M' models, 'S' sub-models); names stored UPPER. Delete blocked when used in
pmctable.
"""

from __future__ import annotations

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.db import Database


class ModelError(Exception):
    pass


class ModelMasterService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def list(self, mtype: str = "M") -> list[dict]:
        if not self.db.table_exists("models"):
            return []
        return self.db.fetchall("SELECT mtype, name FROM models WHERE UPPER(TRIM(mtype)) = :t ORDER BY name",
                                {"t": str(mtype or "M").strip().upper()})

    def save(self, mtype: str, names: list[str]) -> str:
        if not self.db.table_exists("models"):
            raise ModelError("models table not found")
        mtype = str(mtype or "M").strip().upper()
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM models WHERE UPPER(TRIM(mtype)) = :t", {"t": mtype})
            for name in names:
                n = str(name or "").strip()
                if n == "":
                    continue
                tx.execute("INSERT INTO models (mtype, name) VALUES (:t, :n)", {"t": mtype, "n": n.upper()})
        log_delpart(self.db, self.session, ("Sub Models" if mtype == "S" else "Models") + " Saved",
                    utype="E", ttype="R")
        return "Models saved successfully"
