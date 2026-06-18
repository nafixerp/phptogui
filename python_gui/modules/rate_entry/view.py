"""Daily Rate entry window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from .service import RATE_CODES, RateError, RateService

_LABELS = {
    "GRATE": "Gold 22ct", "G18RATE": "Gold 18ct", "G14RATE": "Gold 14ct",
    "G9RATE": "Gold 9ct", "G4RATE": "Gold 4ct", "OGRATE": "Old Gold",
    "THRATE": "TH (24ct)", "PRATE": "Platinum", "SRATE": "Silver",
    "JRATE": "Smith Rate", "OSRATE": "Old Silver", "BULRATE": "Bullion",
    "BULTOUCH": "Bullion Touch",
}


class RateEntryView(ctk.CTkFrame):
    TITLE = "Daily Rates"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = RateService(database, session)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="Save Rates", width=110, command=self._save).pack(side="right", padx=6)
        body = ctk.CTkScrollableFrame(self); body.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        body.grid_columnconfigure(1, weight=1)
        self.entries: dict[str, ctk.CTkEntry] = {}
        current = {}
        try:
            current = self.service.current()
        except Exception:
            pass
        for i, code in enumerate(RATE_CODES):
            ctk.CTkLabel(body, text=_LABELS.get(code, code), anchor="w", width=160).grid(row=i, column=0, sticky="w", padx=8, pady=3)
            e = ctk.CTkEntry(body, width=160); e.grid(row=i, column=1, sticky="w", padx=8, pady=3)
            e.insert(0, f'{float(current.get(code, 0)):.3f}')
            self.entries[code] = e
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=4)
        if not self.service.can_edit():
            self.status.configure(text="You do not have permission to update rates (read-only).", text_color="#C0392B")

    def _save(self):
        values = {code: (e.get() or "0") for code, e in self.entries.items()}
        try:
            msg = self.service.save(values)
        except (RateError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=msg, text_color="#1E8449")
