"""Customer Opening Bills window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from .service import CustomerOpBillsService, OpBillError


class CustomerOpBillsView(ctk.CTkFrame):
    TITLE = "Customer Opening Bills"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = CustomerOpBillsService(PostingEngine(database), session)
        self._rows = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Customer").pack(side="left", padx=(16, 4))
        self.cust = ctk.CTkEntry(head, width=110); self.cust.pack(side="left")
        ctk.CTkLabel(head, text="Name").pack(side="left", padx=(8, 4))
        self.cname = ctk.CTkEntry(head, width=150); self.cname.pack(side="left")
        ctk.CTkButton(head, text="Load", width=60, command=self._load).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=[("billno", "Bill No", 120), ("tdate", "Date", 110), ("billamt", "Amount", 130)],
                                    key_field="billno"); self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)
        form = ctk.CTkFrame(self, width=220); form.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)
        ctk.CTkLabel(form, text="Bill No (OP…)").pack(anchor="w", padx=10, pady=(8, 0))
        self.billno = ctk.CTkEntry(form, width=160); self.billno.pack(anchor="w", padx=10)
        ctk.CTkLabel(form, text="Date").pack(anchor="w", padx=10)
        self.tdate = ctk.CTkEntry(form, width=160); self.tdate.pack(anchor="w", padx=10); self.tdate.insert(0, date.today().isoformat())
        ctk.CTkLabel(form, text="Amount").pack(anchor="w", padx=10)
        self.amt = ctk.CTkEntry(form, width=160); self.amt.pack(anchor="w", padx=10)
        ctk.CTkButton(form, text="Add Row", width=100, command=self._add).pack(anchor="w", padx=10, pady=6)
        ctk.CTkButton(form, text="Save Bills", width=160, command=self._save).pack(anchor="w", padx=10)
        self.status = ctk.CTkLabel(form, text="", wraplength=190); self.status.pack(anchor="w", padx=10, pady=6)

    def _load(self):
        try:
            self._rows = [dict(r) for r in self.service.bills_for(self.cust.get())]
            self.grid_widget.set_rows(self._rows)
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _add(self):
        self._rows.append({"billno": self.billno.get(), "tdate": self.tdate.get(), "billamt": self.amt.get()})
        self.grid_widget.set_rows(self._rows)

    def _save(self):
        try:
            res = self.service.save(self.cust.get(), self.cname.get(), self._rows)
        except (OpBillError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._load(); self.status.configure(text=res["message"], text_color="#1E8449")
