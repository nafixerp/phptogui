"""Passbook Print window — party code + date range, build the continuation rows."""
from __future__ import annotations

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from .service import PassbookPrintError, PassbookPrintService


class PassbookPrintView(ctk.CTkFrame):
    TITLE = "Passbook Print"

    def __init__(self, master, database: Database, session: AppSession, mode: str = "scheme"):
        super().__init__(master, fg_color="transparent")
        self.service = PassbookPrintService(database)
        self.mode = mode
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        ctk.CTkLabel(self, text="Party code").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.code = ctk.CTkEntry(self, width=180); self.code.grid(row=1, column=1, sticky="w", padx=12, pady=4)
        ctk.CTkLabel(self, text="From date").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        self.date1 = ctk.CTkEntry(self, width=140); self.date1.grid(row=2, column=1, sticky="w", padx=12, pady=4)
        ctk.CTkLabel(self, text="To date").grid(row=3, column=0, sticky="w", padx=12, pady=4)
        self.date2 = ctk.CTkEntry(self, width=140); self.date2.grid(row=3, column=1, sticky="w", padx=12, pady=4)
        self.reset = ctk.CTkCheckBox(self, text="Reset (print from the beginning)")
        self.reset.grid(row=4, column=1, sticky="w", padx=12, pady=6)
        ctk.CTkButton(self, text="Build Passbook", command=self._build).grid(
            row=5, column=1, sticky="w", padx=12, pady=10)
        self.status = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=640)
        self.status.grid(row=6, column=0, columnspan=2, sticky="ew", padx=14, pady=4)

    def _build(self):
        try:
            res = self.service.build(self.code.get(), date1=self.date1.get(), date2=self.date2.get(),
                                     reset=bool(self.reset.get()))
        except (PassbookPrintError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        s = res["summary"]
        printed = sum(1 for r in res["rows"] if not r.get("blank"))
        self.status.configure(
            text=f"{printed} entries for {res['party']['code']}. Cursor advanced to slno {s['last_slno']}, "
                 f"line {s['last_line']}, passbook no {s['last_passbook_no']}.", text_color="#1E8449")
