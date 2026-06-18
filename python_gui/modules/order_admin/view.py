"""Order Admin window — Rate Fix and Block/Unblock."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import OrderAdminError, OrderAdminService


class OrderAdminView(ctk.CTkFrame):
    TITLE = "Order Rate Fix / Block"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = OrderAdminService(database, gilevel=getattr(session, "gilevel", 1))
        self._sel = None
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Search").pack(side="left", padx=(16, 4))
        self.q = ctk.CTkEntry(head, width=160); self.q.pack(side="left")
        ctk.CTkButton(head, text="Find", width=60, command=self._reload).pack(side="left", padx=6)
        self.rate = ctk.CTkEntry(head, width=100, placeholder_text="rate"); self.rate.pack(side="left", padx=(16, 4))
        ctk.CTkButton(head, text="Rate Fix", width=80, command=self._ratefix).pack(side="left", padx=4)
        ctk.CTkButton(head, text="Block", width=70, command=lambda: self._block(True)).pack(side="left", padx=4)
        ctk.CTkButton(head, text="Unblock", width=80, command=lambda: self._block(False)).pack(side="left", padx=4)
        self.grid_widget = DataGrid(self, columns=[("ordno", "Order No", 120), ("custname", "Customer", 200),
                                    ("billamt", "Bill Amt", 110), ("status", "Status", 70), ("blocked", "Blocked", 80)],
                                    on_select=self._on_select, key_field="ordno")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=4)
        self._reload()

    def _reload(self):
        try:
            rows = self.service.search(self.q.get())
            self.grid_widget.set_rows([{"ordno": str(r["ordno"]), "custname": str(r["custname"]),
                                        "billamt": f'{float(r["billamt"]):.2f}', "status": str(r["status"]),
                                        "blocked": str(r["blocked"])} for r in rows])
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        self._sel = row.get("ordno")

    def _ratefix(self):
        if not self._sel:
            self.status.configure(text="Select an order.", text_color="#C0392B"); return
        try:
            note = self.service.rate_fix(self._sel, self.rate.get())
        except (OrderAdminError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=note, text_color="#1E8449")

    def _block(self, block: bool):
        if not self._sel:
            self.status.configure(text="Select an order.", text_color="#C0392B"); return
        try:
            msg = self.service.set_blocked(self._sel, block)
        except (OrderAdminError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text=msg, text_color="#1E8449")
