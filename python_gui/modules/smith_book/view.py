"""Smith Book window (read-only)."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import SmithBookService


class SmithBookView(ctk.CTkFrame):
    TITLE = "Smith Book"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = SmithBookService(database, rlevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Smith").pack(side="left", padx=(16, 4))
        self.code = ctk.CTkEntry(head, width=100); self.code.pack(side="left")
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(12, 4))
        self.d1 = ctk.CTkEntry(head, width=110); self.d1.pack(side="left"); self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(12, 4))
        self.d2 = ctk.CTkEntry(head, width=110); self.d2.pack(side="left"); self.d2.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)

        self.summary = ctk.CTkLabel(self, text="", anchor="w")
        self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("tdate", "Date", 100), ("docno", "Doc", 100),
                                    ("issued_wgt", "Issued", 100), ("received_wgt", "Received", 100),
                                    ("netamt", "Net Amt", 110)], key_field="slno")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _show(self):
        try:
            res = self.service.transactions(self.code.get(), self.d1.get(), self.d2.get())
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        rows = [{"slno": r["slno"], "tdate": str(r["tdate"]), "docno": str(r.get("docno") or ""),
                 "issued_wgt": f'{r["issued_wgt"]:.3f}', "received_wgt": f'{r["received_wgt"]:.3f}',
                 "netamt": f'{float(r["netamt"]):.2f}'} for r in res["rows"]]
        self.grid_widget.set_rows(rows)
        self.summary.configure(
            text=f"Issued: {res['issued']:.3f}    Received: {res['received']:.3f}    Balance: {res['balance']:.3f}",
            text_color=("gray20", "gray80"))
