"""GST Summary window (read-only)."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from .service import GstSummaryService


class GstReportView(ctk.CTkFrame):
    TITLE = "GST Summary"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = GstSummaryService(database, gilevel=getattr(session, "gilevel", 1))
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 8))
        bar = ctk.CTkFrame(self); bar.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(bar, text="From").pack(side="left", padx=(12, 4))
        self.d1 = ctk.CTkEntry(bar, width=120); self.d1.pack(side="left")
        self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(bar, text="To").pack(side="left", padx=(12, 4))
        self.d2 = ctk.CTkEntry(bar, width=120); self.d2.pack(side="left")
        self.d2.insert(0, date.today().isoformat())
        ctk.CTkButton(bar, text="Show", width=80, command=self._show).pack(side="left", padx=12)

        self.card = ctk.CTkFrame(self); self.card.pack(fill="x", padx=16, pady=8)
        self.labels = {}
        for key, label in [("taxable", "Taxable (RS)"), ("sgst", "SGST"), ("cgst", "CGST"),
                           ("igst", "IGST"), ("total_tax", "Total Tax")]:
            row = ctk.CTkFrame(self.card, fg_color="transparent"); row.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(row, text=label, width=160, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
            v = ctk.CTkLabel(row, text="—", anchor="w"); v.pack(side="left")
            self.labels[key] = v

    def _show(self):
        try:
            s = self.service.summary(self.d1.get(), self.d2.get())
        except Exception as exc:
            self.labels["taxable"].configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        for key, lbl in self.labels.items():
            lbl.configure(text=f"{abs(s[key]):.2f}")
