"""Account Ledger window (read-only report)."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import AccountLedgerService


class AccountLedgerView(ctk.CTkFrame):
    TITLE = "Account Ledger"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = AccountLedgerService(database, gilevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="A/c Code").pack(side="left", padx=(16, 4))
        self.code = ctk.CTkEntry(head, width=120); self.code.pack(side="left")
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(12, 4))
        self.dfrom = ctk.CTkEntry(head, width=110); self.dfrom.pack(side="left")
        self.dfrom.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(12, 4))
        self.dto = ctk.CTkEntry(head, width=110); self.dto.pack(side="left")
        self.dto.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)

        self.summary = ctk.CTkLabel(self, text="", anchor="w")
        self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("date", "Date", 90), ("vchno", "Vch No", 90),
                                    ("othacname", "Particulars", 200), ("debit", "Debit", 100),
                                    ("credit", "Credit", 100), ("balance", "Balance", 120)], key_field="vchno")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _show(self):
        try:
            led = self.service.ledger(self.code.get(), self.dfrom.get(), self.dto.get())
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        rows = [{"date": r["date"], "vchno": r["vchno"], "othacname": r["othacname"],
                 "debit": f'{r["debit"]:.2f}' if r["debit"] else "",
                 "credit": f'{r["credit"]:.2f}' if r["credit"] else "",
                 "balance": f'{r["running_balance"]:.2f} {r["running_side"]}'} for r in led["rows"]]
        self.grid_widget.set_rows(rows)
        self.summary.configure(
            text=f"Opening: {led['opening']:.2f} {led['opening_side']}    "
                 f"Closing: {led['closing']:.2f} {led['closing_side']}    Rows: {len(rows)}",
            text_color=("gray20", "gray80"))
