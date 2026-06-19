"""Account Restart Date window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from .service import AccountRestartDateError, AccountRestartDateService


class AccountRestartDateView(ctk.CTkFrame):
    TITLE = "Account Restart Date"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = AccountRestartDateService(database)
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        ctk.CTkLabel(self, text="Account Code").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.code = ctk.CTkEntry(self, width=180); self.code.grid(row=1, column=1, sticky="w", padx=12, pady=4)
        ctk.CTkButton(self, text="Load", width=70, command=self._load).grid(row=1, column=2, padx=6)
        ctk.CTkLabel(self, text="Restart Date").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        self.opdate = ctk.CTkEntry(self, width=180); self.opdate.grid(row=2, column=1, sticky="w", padx=12, pady=4)
        ctk.CTkButton(self, text="Save", width=100, command=self._save).grid(row=3, column=1, sticky="w", padx=12, pady=10)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=4, column=0, columnspan=3, sticky="ew", padx=14, pady=4)

    def _load(self):
        r = self.service.load(self.code.get())
        if not r:
            self.status.configure(text="Account not found.", text_color="#C0392B"); return
        self.opdate.delete(0, "end"); self.opdate.insert(0, str(r.get("opdate") or ""))
        self.status.configure(text=f'{r.get("name") or ""}', text_color=("gray20", "gray80"))

    def _save(self):
        try:
            msg = self.service.save(self.code.get(), self.opdate.get())
        except (AccountRestartDateError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=msg, text_color="#1E8449")
