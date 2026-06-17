"""Counters rules — port of CountersController (save/delete)."""

from __future__ import annotations

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import to_decimal
from .repo import CountersRepo


class CountersError(Exception):
    pass


class CountersService:
    def __init__(self, repo: CountersRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    def list(self) -> list[dict]:
        return self.repo.list()

    def save(self, code: str, name: str, startbillno) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise CountersError("No code given.")
        name = str(name or "").strip().upper()
        start = int(to_decimal(startbillno) or 0)
        with self.repo.db.transaction() as tx:
            self.repo.upsert(tx, code, name, start)
            # Seed generali bill-no only if startbillno>0 and counter has no sales yet
            if start > 0 and self.repo.has_generali() and self.repo.sales_count(code) == 0:
                self.repo.seed_generali(tx, code, start)
        log_delpart(self.repo.db, self.session, "Counters Saved", utype="E", ttype="R")
        return "Saved successfully."

    def delete(self, code: str) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise CountersError("No row selected.")
        if self.repo.used_in_barcode(code):
            raise CountersError("You can't delete this entry!")
        self.repo.delete(code)
        log_delpart(self.repo.db, self.session, f"Counter({code}) Deleted", utype="D", ttype="R")
        return "Deleted successfully."
