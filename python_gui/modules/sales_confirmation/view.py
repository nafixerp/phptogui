"""Sales Bill Confirmation window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import ConfirmError, SalesConfirmationService


class SalesConfirmationView(ctk.CTkFrame):
    TITLE = "Sales Bill Confirmation"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = SalesConfirmationService(database, session)
        self._sel = None
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(16, 4))
        self.d1 = ctk.CTkEntry(head, width=110); self.d1.pack(side="left"); self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(8, 4))
        self.d2 = ctk.CTkEntry(head, width=110); self.d2.pack(side="left"); self.d2.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Show", width=70, command=self._reload).pack(side="left", padx=8)
        ctk.CTkButton(head, text="Confirm Selected", width=140, command=self._confirm).pack(side="right", padx=6)
        self.grid_widget = DataGrid(self, columns=[("billno", "Bill No", 110), ("tdate", "Date", 100),
                                    ("custname", "Customer", 200), ("netamt", "Net Amt", 120), ("status", "Status", 70)],
                                    on_select=self._on_select, key_field="slno")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=4)
        self._reload()

    def _reload(self):
        try:
            rows = self.service.pending(self.d1.get(), self.d2.get())
            self.grid_widget.set_rows([{"slno": r["slno"], "billno": str(r.get("billno") or ""), "tdate": str(r.get("tdate") or ""),
                                        "custname": str(r.get("custname") or ""), "netamt": f'{float(r.get("netamt") or 0):.2f}', "status": str(r.get("status") or "")} for r in rows])
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        self._sel = row.get("slno")

    def _confirm(self):
        if self._sel is None:
            self.status.configure(text="Select a bill.", text_color="#C0392B"); return
        try:
            msg = self.service.confirm(self._sel, True)
        except (ConfirmError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text=msg, text_color="#1E8449")
