"""Item Sub-Group rules — port of ItemSubGroupController (save/delete)."""

from __future__ import annotations

from ...core.audit import log_delpart
from ...core.auth import AppSession
from .repo import ItemSubGroupRepo


class ItemSubGroupError(Exception):
    pass


class ItemSubGroupService:
    def __init__(self, repo: ItemSubGroupRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    def list(self) -> list[dict]:
        return self.repo.list()

    def save(self, code: str, name: str) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise ItemSubGroupError("Code is required.")
        self.repo.upsert(code, str(name or "").strip())
        log_delpart(self.repo.db, self.session, "Item Sub Groups Saved", utype="E", ttype="R")
        return "Saved."

    def delete(self, code: str) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise ItemSubGroupError("Code is required for delete.")
        if self.repo.used_in_barcode(code) > 0:
            raise ItemSubGroupError("Cannot delete: used in barcode table.")
        if self.repo.delete(code) < 1:
            raise ItemSubGroupError("Sub group not found.")
        log_delpart(self.repo.db, self.session, f"Item Sub Group({code}) Deleted", utype="D", ttype="R")
        return "Sub group deleted successfully."
