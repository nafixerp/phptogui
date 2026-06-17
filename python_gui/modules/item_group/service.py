"""Item Group rules — port of ItemGroupController::save (modes A/E/D).

itype ∈ {G,S,P,O} (default G); orn/showinstkrep stored Y/N; pos int. Delete
blocked when items exist in the group.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import to_decimal
from .repo import ItemGroupRepo


class ItemGroupError(Exception):
    pass


@dataclass
class ItemGroupForm:
    code: str = ""
    name: str = ""
    mname: str = ""
    type: str = "G"
    ornament: bool = False
    position: object = 0
    show_in_stock: bool = False


class ItemGroupService:
    def __init__(self, repo: ItemGroupRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    def list(self, search: str = "") -> list[dict]:
        return self.repo.list(search.strip())

    def get(self, code: str) -> dict | None:
        return self.repo.get(code)

    def _payload(self, f: ItemGroupForm) -> dict:
        itype = str(f.type or "G").strip().upper()
        if itype not in ("G", "S", "P", "O"):
            itype = "G"
        return {
            "name": str(f.name or "").strip(),
            "mname": str(f.mname or "").strip(),
            "itype": itype,
            "orn": "Y" if f.ornament else "N",
            "pos": int(to_decimal(f.position) or 0),
            "showinstkrep": "Y" if f.show_in_stock else "N",
        }

    def save(self, f: ItemGroupForm, mode: str) -> str:
        mode = str(mode or "A").strip().upper()
        if mode not in ("A", "E"):
            raise ItemGroupError("Invalid operation mode.")
        code = str(f.code or "").strip().upper()
        if code == "":
            raise ItemGroupError("Group code is required.")
        if str(f.name or "").strip() == "":
            raise ItemGroupError("Group name is required.")
        payload = self._payload(f)
        if mode == "A":
            if self.repo.exists(code):
                raise ItemGroupError("Code already exists.")
            payload["code"] = code
            self.repo.insert(payload)
            log_delpart(self.repo.db, self.session, f"Item Group({code}) Added", utype="A", ttype="R")
            return "Group added successfully."
        if self.repo.update(code, payload) < 1:
            raise ItemGroupError("Group not found.")
        log_delpart(self.repo.db, self.session, f"Item Group({code}) Updated", utype="E", ttype="R")
        return "Group updated successfully."

    def delete(self, code: str) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise ItemGroupError("Group code is required.")
        if self.repo.items_in_group(code) > 0:
            raise ItemGroupError("Cannot delete: items exist in this group.")
        if self.repo.delete(code) < 1:
            raise ItemGroupError("Group not found.")
        log_delpart(self.repo.db, self.session, f"Item Group({code}) Deleted", utype="D", ttype="R")
        return "Group deleted successfully."
