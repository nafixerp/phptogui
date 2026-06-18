"""Order Cancel window."""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import OrderCancelError, OrderCancelService


class OrderCancelView(ctk.CTkFrame):
    TITLE = "Order Cancel"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = OrderCancelService(database, session)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.search_var = ctk.StringVar()
        e = ctk.CTkEntry(head, width=200, placeholder_text="Search order…", textvariable=self.search_var)
        e.pack(side="right"); e.bind("<Return>", lambda _ev: self._reload())
        ctk.CTkButton(head, text="Search", width=70, command=self._reload).pack(side="right", padx=6)
        ctk.CTkButton(head, text="Cancel Order", width=110, fg_color="#B03A2E",
                      hover_color="#943126", command=self._cancel).pack(side="right", padx=6)

        self.grid_widget = DataGrid(self, columns=[("ordno", "Order No", 90), ("custname", "Customer", 180),
                                    ("tdate", "Date", 100), ("closed", "Closed", 70)],
                                    on_select=self._sel, key_field="ordno")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=4)
        self._sel_ordno = None
        self._reload()

    def _reload(self):
        try:
            self.grid_widget.set_rows(self.service.search(self.search_var.get()))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _sel(self, row):
        self._sel_ordno = row.get("ordno")

    def _cancel(self):
        if self._sel_ordno is None:
            self.status.configure(text="Select an order.", text_color="#C0392B"); return
        if not messagebox.askyesno("Cancel Order", f"Cancel order #{self._sel_ordno}? This reverses its advance posting."):
            return
        try:
            self.service.cancel(self._sel_ordno)
        except (OrderCancelError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text=f"Order #{self._sel_ordno} cancelled.", text_color="#1E8449")
