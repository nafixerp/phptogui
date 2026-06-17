"""MC Table rules — port of MCTableController::save (bulk replace per code+iqtype)."""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import to_decimal
from .repo import MCTableRepo

_NUM = ["weight1", "weight2", "mc", "mcpergm", "mcperqty", "vaperc"]


class MCTableError(Exception):
    pass


class MCTableService:
    def __init__(self, repo: MCTableRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    def get_for_item(self, code: str, iqtype: str = "") -> list[dict]:
        return self.repo.get_for_item(code, iqtype)

    def save(self, code: str, iqtype: str, entries: list[dict]) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise MCTableError("Item code is required.")
        norm = []
        for e in entries:
            norm.append({k: (to_decimal(e.get(k, 0)) or Decimal("0")) for k in _NUM})
        n = self.repo.bulk_update(code, str(iqtype or "").strip(), norm)
        log_delpart(self.repo.db, self.session, f"MC Table({code}) Updated", utype="E", ttype="R")
        return f"MC Table updated successfully ({n} slab(s))."
