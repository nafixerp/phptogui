"""Gift Table — `gifttable(points PK, particulars)`. Source: GiftTableController.

Per-row upsert keyed on `points`; renaming the points value deletes the old row.
"""

from __future__ import annotations

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import to_decimal


class GiftError(Exception):
    pass


class GiftTableService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def list(self) -> list[dict]:
        if not self.db.table_exists("gifttable"):
            return []
        return self.db.fetchall("SELECT points, particulars FROM gifttable ORDER BY points")

    def _exists(self, points: int) -> bool:
        return self.db.fetchone("SELECT 1 FROM gifttable WHERE points = :p LIMIT 1", {"p": points}) is not None

    def save(self, points, particulars: str, orig_points=None) -> str:
        if points in (None, ""):
            raise GiftError("Points is required")
        pts = int(to_decimal(points) or 0)
        part = str(particulars or "").strip()[:60]
        orig = None if orig_points in (None, "") else int(to_decimal(orig_points) or 0)
        with self.db.transaction() as tx:
            if orig is not None and orig != pts:
                tx.execute("DELETE FROM gifttable WHERE points = :p", {"p": orig})
            if tx.scalar("SELECT 1 FROM gifttable WHERE points = :p LIMIT 1", {"p": pts}):
                tx.execute("UPDATE gifttable SET particulars = :pa WHERE points = :p", {"pa": part, "p": pts})
            else:
                tx.execute("INSERT INTO gifttable (points, particulars) VALUES (:p, :pa)", {"p": pts, "pa": part})
        log_delpart(self.db, self.session, "Gift Table Saved", utype="E", ttype="R")
        return "Saved."

    def delete(self, points) -> str:
        pts = int(to_decimal(points) or 0)
        self.db.execute("DELETE FROM gifttable WHERE points = :p", {"p": pts})
        return "Deleted."
