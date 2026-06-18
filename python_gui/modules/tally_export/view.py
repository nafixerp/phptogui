"""Tally Export window."""

from __future__ import annotations

from datetime import date
from tkinter import filedialog

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from .service import TallyExportService


class TallyExportView(ctk.CTkFrame):
    TITLE = "Tally Export"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = TallyExportService(database, gilevel=getattr(session, "gilevel", 1))
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 8))
        bar = ctk.CTkFrame(self); bar.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(bar, text="From").pack(side="left", padx=(12, 4))
        self.d1 = ctk.CTkEntry(bar, width=120); self.d1.pack(side="left")
        self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(bar, text="To").pack(side="left", padx=(12, 4))
        self.d2 = ctk.CTkEntry(bar, width=120); self.d2.pack(side="left")
        self.d2.insert(0, date.today().isoformat())
        ctk.CTkButton(bar, text="Export Tally XML", width=150, command=self._export).pack(side="left", padx=12)
        self.status = ctk.CTkLabel(self, text="", wraplength=560); self.status.pack(anchor="w", padx=16, pady=8)

    def _export(self):
        path = filedialog.asksaveasfilename(defaultextension=".xml",
                                            initialfile=f"tally-{self.d1.get()}-to-{self.d2.get()}.xml",
                                            filetypes=[("Tally XML", "*.xml")])
        if not path:
            return
        try:
            n = self.service.export_to_file(self.d1.get(), self.d2.get(), path)
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=f"Exported {n} voucher(s) to {path}", text_color="#1E8449")
