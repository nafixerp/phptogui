"""Application Settings window (DB-backed shop info + counters)."""

from __future__ import annotations

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from .repo import AppSettingsRepo
from .service import AppSettingsService

_FIELDS = [
    ("name", "Shop Name"), ("address", "Shop Address"), ("phone", "Shop Phone"),
    ("clastno", "Customer Last No (CLASTNO)"), ("slastno", "Supplier Last No (SLASTNO)"),
    ("sbpref", "Barcode Prefix (SBPREF)"), ("sblen", "Barcode Length (SBLEN)"),
]


class AppSettingsView(ctk.CTkFrame):
    TITLE = "Application Settings"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = AppSettingsService(AppSettingsRepo(database), session)
        self._entries: dict[str, ctk.CTkEntry] = {}

        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 8))
        card = ctk.CTkFrame(self); card.pack(fill="x", padx=16, pady=8)
        for key, label in _FIELDS:
            row = ctk.CTkFrame(card, fg_color="transparent"); row.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(row, text=label, width=220, anchor="w").pack(side="left")
            e = ctk.CTkEntry(row, width=280); e.pack(side="left")
            self._entries[key] = e

        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(anchor="w", padx=16, pady=8)
        ctk.CTkButton(bar, text="Reload", width=90, command=self._load).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="Save", width=90, command=self._save).pack(side="left")
        self.status = ctk.CTkLabel(self, text="", wraplength=520); self.status.pack(anchor="w", padx=16)
        self._load()

    def _load(self):
        try:
            data = self.service.load()
            for key, e in self._entries.items():
                e.delete(0, "end"); e.insert(0, str(data.get(key, "")))
            self.status.configure(text="Loaded.", text_color=("gray30", "gray70"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _save(self):
        data = {k: e.get() for k, e in self._entries.items()}
        try:
            msg = self.service.save(data)
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=msg, text_color="#1E8449")
