"""Denomination Master rules — port of DenominationMasterController save."""

from __future__ import annotations

from decimal import Decimal

from ...core.auth import AppSession
from ...core.decimals import to_decimal
from .repo import DenominationRepo


class DenominationError(Exception):
    pass


class DenominationService:
    def __init__(self, repo: DenominationRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    def list(self) -> list[dict]:
        return self.repo.list()

    def save(self, code: str, name: str, cvalue) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise DenominationError("Code is required.")
        self.repo.upsert(code, str(name or "").strip(), to_decimal(cvalue) or Decimal("0"))
        return "Saved successfully."

    def delete(self, code: str) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise DenominationError("Code is required.")
        self.repo.delete(code)
        return "Deleted successfully."
