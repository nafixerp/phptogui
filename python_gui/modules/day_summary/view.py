"""Day Summary window (read-only)."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import DaySummaryService


class DaySummaryView(ctk.CTkFrame):
    TITLE = "Day Summary"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = DaySummaryService(database, rlevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(16, 4))
        self.d1 = ctk.CTkEntry(head, width=110); self.d1.pack(side="left"); self.d1.insert(0, date.today().replace(day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(12, 4))
        self.d2 = ctk.CTkEntry(head, width=110); self.d2.pack(side="left"); self.d2.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("date", "Date", 130), ("debit", "Debit", 150),
                                    ("credit", "Credit", 150), ("net", "Net", 150)], key_field="date")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _show(self):
        try:
            res = self.service.summary(self.d1.get(), self.d2.get())
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        rows = [{"date": r["date"], "debit": f'{r["debit"]:.2f}', "credit": f'{r["credit"]:.2f}', "net": f'{r["net"]:.2f}'} for r in res["rows"]]
        self.grid_widget.set_rows(rows)
        self.summary.configure(text=f"Total Debit: {res['total_debit']:.2f}    Total Credit: {res['total_credit']:.2f}",
                               text_color=("gray20", "gray80"))
