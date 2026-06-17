"""Day Book window (read-only)."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import DayBookService


class DayBookView(ctk.CTkFrame):
    TITLE = "Day Book"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = DayBookService(database, gilevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(16, 4))
        self.dfrom = ctk.CTkEntry(head, width=110); self.dfrom.pack(side="left")
        self.dfrom.insert(0, date.today().isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(12, 4))
        self.dto = ctk.CTkEntry(head, width=110); self.dto.pack(side="left")
        self.dto.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)

        self.summary = ctk.CTkLabel(self, text="", anchor="w")
        self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("date", "Date", 90), ("vchno", "Vch No", 90),
                                    ("accode", "Account", 90), ("acname", "Name", 180),
                                    ("debit", "Debit", 100), ("credit", "Credit", 100)], key_field="vchno")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _show(self):
        try:
            bal = self.service.cash_balances(self.dfrom.get(), self.dto.get())
            entries = self.service.entries(self.dfrom.get(), self.dto.get())
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        rows = [{"date": e["date"], "vchno": e["vchno"], "accode": e["accode"], "acname": e["acname"],
                 "debit": f'{e["debit"]:.2f}' if e["debit"] else "",
                 "credit": f'{e["credit"]:.2f}' if e["credit"] else ""} for e in entries]
        self.grid_widget.set_rows(rows)
        self.summary.configure(
            text=f"Cash Opening: {bal['opbal']:.2f}    Cash Closing: {bal['clbal']:.2f}    Entries: {len(rows)}",
            text_color=("gray20", "gray80"))
