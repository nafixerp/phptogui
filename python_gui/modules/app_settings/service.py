"""Application Settings rules — DB-backed subset of ApplicationSettingsController.

Loads/saves shop info (generals) + CLASTNO/SLASTNO (generali) + SBPREF/SBLEN
(generals). persistGeneraliCounter ignores blank values (matches the controller).
The INI-file app/printer preferences and logo upload are not DB-backed and are
intentionally out of scope here (documented in docs/phase1-2-remaining.md).
"""

from __future__ import annotations

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import to_decimal
from .repo import AppSettingsRepo


class AppSettingsService:
    def __init__(self, repo: AppSettingsRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    def load(self) -> dict:
        return {
            "name": self.repo.generals_value("SHOPNM"),
            "address": self.repo.generals_value("SHOPADDR"),
            "phone": self.repo.generals_value("SHOPPHONE"),
            "clastno": self.repo.generali_value("CLASTNO", "0"),
            "slastno": self.repo.generali_value("SLASTNO", "0"),
            "sbpref": self.repo.generals_value("SBPREF", ""),
            "sblen": self.repo.generals_value("SBLEN", "5"),
        }

    def save(self, data: dict) -> str:
        with self.repo.db.transaction() as tx:
            self.repo.set_generals(tx, "SHOPNM", str(data.get("name") or "").strip())
            self.repo.set_generals(tx, "SHOPADDR", str(data.get("address") or "").strip())
            self.repo.set_generals(tx, "SHOPPHONE", str(data.get("phone") or "").strip())
            # counters: blank value is ignored (persistGeneraliCounter)
            for code, key in (("CLASTNO", "clastno"), ("SLASTNO", "slastno")):
                val = str(data.get(key, "")).strip()
                if val != "":
                    self.repo.set_generali(tx, code, int(to_decimal(val) or 0))
            if "sbpref" in data:
                self.repo.set_generals(tx, "SBPREF", str(data.get("sbpref") or "").strip())
            if "sblen" in data:
                self.repo.set_generals(tx, "SBLEN", str(data.get("sblen") or "").strip())
        log_delpart(self.repo.db, self.session, "Application Settings Saved", utype="E", ttype="R")
        return "Application settings saved."
