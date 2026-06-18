"""Staff Transaction window (post)."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from .service import StaffError, StaffTransactionService


class StaffTransactionView(ctk.CTkFrame):
    TITLE = "Staff Transaction"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = StaffTransactionService(PostingEngine(database), session)
        self._items: list[dict] = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Date").pack(side="left", padx=(16, 4))
        self.tdate = ctk.CTkEntry(head, width=110); self.tdate.pack(side="left"); self.tdate.insert(0, date.today().isoformat())
        ctk.CTkLabel(head, text="Contra A/c").pack(side="left", padx=(12, 4))
        self.accode = ctk.CTkEntry(head, width=90); self.accode.pack(side="left"); self.accode.insert(0, "CASH")
        self.is_debit = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(head, text="Debit (pay out)", variable=self.is_debit).pack(side="left", padx=12)

        self.grid_widget = DataGrid(self, columns=[("code", "Staff A/c", 140), ("amount", "Amount", 140)],
                                    key_field="code")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)
        form = ctk.CTkFrame(self, width=220); form.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)
        ctk.CTkLabel(form, text="Staff A/c").pack(anchor="w", padx=10, pady=(8, 0))
        self.code = ctk.CTkEntry(form, width=160); self.code.pack(anchor="w", padx=10)
        ctk.CTkLabel(form, text="Amount").pack(anchor="w", padx=10)
        self.amount = ctk.CTkEntry(form, width=160); self.amount.pack(anchor="w", padx=10)
        ctk.CTkButton(form, text="Add Row", width=100, command=self._add).pack(anchor="w", padx=10, pady=6)
        ctk.CTkButton(form, text="Save", width=160, command=self._save).pack(anchor="w", padx=10)
        self.status = ctk.CTkLabel(form, text="", wraplength=190); self.status.pack(anchor="w", padx=10, pady=6)

    def _add(self):
        self._items.append({"code": self.code.get(), "amount": self.amount.get()})
        self.grid_widget.set_rows(self._items)

    def _save(self):
        try:
            res = self.service.save(self._items, self.accode.get(), self.is_debit.get(), self.tdate.get())
        except (StaffError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._items = []; self.grid_widget.set_rows([])
        self.status.configure(text=f"Saved {res['vchno']} (slno {res['slno']}).", text_color="#1E8449")
