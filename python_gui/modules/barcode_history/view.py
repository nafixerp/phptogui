"""Barcode History window — movement timeline for a single barcode."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import BarcodeHistoryService


class BarcodeHistoryView(ctk.CTkFrame):
    TITLE = "Barcode History"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = BarcodeHistoryService(database, gilevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Barcode").pack(side="left", padx=(16, 4))
        self.bcode = ctk.CTkEntry(head, width=120); self.bcode.pack(side="left")
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[
            ("tdate", "Date", 100), ("transaction", "Transaction", 150), ("docno", "Doc No", 110),
            ("qty", "Qty", 60), ("weight", "Weight", 100), ("stone", "Stone", 100), ("rate", "Rate", 100)], key_field="_k")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _show(self):
        try:
            bc = (self.bcode.get() or "").strip()
            if not bc:
                return
            info = self.service.info(int(bc))
            rows = self.service.history(int(bc))
            self.grid_widget.set_rows([{
                "_k": i, "tdate": r["tdate"], "transaction": r["transaction"], "docno": r["docno"],
                "qty": r["qty"], "weight": f'{r["weight"]:.3f}', "stone": f'{r["stone"]:.3f}',
                "rate": f'{r["rate"]:.2f}'} for i, r in enumerate(rows)])
            name = (info or {}).get("itemname", "")
            self.summary.configure(text=f'{name}: {len(rows)} movement(s).', text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
