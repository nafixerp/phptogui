"""Repair Complaints master — port of RepairComplaintsController.

`repcompl` is a single-column (``part``) list of complaint texts. ``save``
deletes the listed rows and upserts the remaining ones by ``part`` (upper-cased,
de-duplicated), all in one transaction.
"""

from __future__ import annotations

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.db import Database


class RepairComplaintsService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def list(self) -> list[str]:
        if not self.db.table_exists("repcompl"):
            return []
        rows = self.db.fetchall("SELECT part FROM repcompl ORDER BY part")
        return [str(r.get("part") or "").strip() for r in rows if str(r.get("part") or "").strip()]

    def save(self, rows: list[str], deleted: list[str] | None = None) -> str:
        if not self.db.table_exists("repcompl"):
            raise RuntimeError("`repcompl` table not found.")
        deleted = deleted or []
        seen: set[str] = set()
        with self.db.transaction() as tx:
            for part in deleted:
                part = str(part).strip()
                if part:
                    tx.execute("DELETE FROM repcompl WHERE part = :p", {"p": part})
            for row in rows:
                part = str(row).strip().upper()
                if not part or part in seen:
                    continue
                seen.add(part)
                exists = tx.fetchall("SELECT 1 FROM repcompl WHERE part = :p LIMIT 1", {"p": part})
                if not exists:
                    tx.execute("INSERT INTO repcompl (part) VALUES (:p)", {"p": part})
        log_delpart(self.db, self.session, "Repair Complaints Saved", utype="E", ttype="T")
        return "Saved successfully"
