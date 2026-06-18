"""Barcode Stock List + Stock Verification windows."""

from __future__ import annotations

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import BarcodeStockService


class BarcodeStockListView(ctk.CTkFrame):
    TITLE = "Barcode Stock List"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = BarcodeStockService(database)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Counter").pack(side="left", padx=(16, 4))
        self.counter = ctk.CTkEntry(head, width=90); self.counter.pack(side="left")
        ctk.CTkLabel(head, text="Item").pack(side="left", padx=(12, 4))
        self.icode = ctk.CTkEntry(head, width=90); self.icode.pack(side="left")
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w")
        self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("bcode", "Barcode", 90), ("icode", "Item", 90),
                                    ("qty", "Qty", 60), ("weight", "Weight", 90), ("qtype", "Purity", 70),
                                    ("counter", "Counter", 80)], key_field="bcode")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._show()

    def _show(self):
        try:
            res = self.service.list_stock(self.counter.get(), self.icode.get())
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        rows = [{**r, "weight": f'{float(r["weight"]):.3f}'} for r in res["rows"]]
        self.grid_widget.set_rows(rows)
        self.summary.configure(text=f"In stock: {len(rows)}    Qty: {res['total_qty']}    "
                                    f"Weight: {res['total_weight']:.3f}", text_color=("gray20", "gray80"))


class StockVerificationView(ctk.CTkFrame):
    TITLE = "Stock Verification"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = BarcodeStockService(database)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))
        bar = ctk.CTkFrame(self); bar.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(bar, text="Scan Barcode #").pack(side="left", padx=(12, 4))
        self.bcode = ctk.CTkEntry(bar, width=140); self.bcode.pack(side="left")
        self.bcode.bind("<Return>", lambda _e: self._scan())
        ctk.CTkButton(bar, text="Verify", width=90, command=self._scan).pack(side="left", padx=10)
        self.card = ctk.CTkFrame(self); self.card.pack(fill="x", padx=16, pady=8)
        self.result = ctk.CTkLabel(self.card, text="Scan a barcode to verify.", anchor="w", justify="left")
        self.result.pack(anchor="w", padx=12, pady=12)

    def _scan(self):
        try:
            b = int(self.bcode.get())
        except ValueError:
            self.result.configure(text="Invalid barcode number", text_color="#C0392B"); return
        info = self.service.lookup(b)
        if not info:
            self.result.configure(text=f"Barcode {b} not found", text_color="#C0392B"); return
        status = "IN STOCK" if info["in_stock"] else ("OUT OF STOCK (sold)" if info["out_of_stock"] else info["stk"])
        color = "#1E8449" if info["in_stock"] else "#C0392B"
        self.result.configure(
            text=f"Barcode {info['bcode']}  —  {status}\n"
                 f"Item: {info['icode']}  {info['itemname']}\n"
                 f"Weight: {info['weight']}   Purity: {info['qtype']}   Counter: {info['counter']}",
            text_color=color)
