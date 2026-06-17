"""Purity Type rules — port of ItemPurityTypeController per-row save + delete.

normalizeTouch: keep digits + one decimal point; rename to a new code cascades
to related tables; delete blocked when the code is in use.
"""

from __future__ import annotations

import re
from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from .repo import PurityTypeRepo


class PurityTypeError(Exception):
    pass


def normalize_touch(value) -> Decimal:
    raw = str(value or "").strip()
    if raw == "":
        return Decimal("0")
    raw = raw.replace(",", ".")
    raw = re.sub(r"[^0-9.]", "", raw) or "0"
    parts = raw.split(".")
    if len(parts) > 2:
        raw = parts[0] + "." + "".join(parts[1:])
    try:
        return Decimal(raw)
    except Exception:
        return Decimal("0")


class PurityTypeService:
    def __init__(self, repo: PurityTypeRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    def list(self) -> list[dict]:
        return self.repo.list()

    def save_row(self, code: str, touch, original_code: str = "") -> str:
        """Port of one iteration of save()'s loop."""
        code = str(code or "").strip().upper()
        original = str(original_code or code).strip().upper()
        if code == "":
            raise PurityTypeError("Purity code is required.")
        touch_val = normalize_touch(touch)

        existing = self.repo.exists(original)
        with self.repo.db.transaction() as tx:
            if existing:
                if code != original and self.repo.exists(code):
                    raise PurityTypeError(f'Purity code "{code}" already exists.')
                self.repo.update(tx, original, code, touch_val)
                if code != original:
                    self.repo.cascade_rename(tx, original, code)
            else:
                if self.repo.exists(code):
                    self.repo.update_touch(tx, code, touch_val)
                else:
                    self.repo.insert(tx, code, touch_val)
        log_delpart(self.repo.db, self.session, "Purity Types Saved", utype="E", ttype="R")
        return "Saved."

    def delete(self, code: str) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise PurityTypeError("Code is required.")
        usage = self.repo.usage_count(code)
        if usage > 0:
            raise PurityTypeError(f'Cannot delete "{code}" - code is in use in {usage} record(s).')
        with self.repo.db.transaction() as tx:
            self.repo.delete(tx, code)
        log_delpart(self.repo.db, self.session, f"Purity Type({code}) Deleted", utype="D", ttype="R")
        return "Deleted."
