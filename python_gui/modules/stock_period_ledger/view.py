"""Stock Period Ledger window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import StockPeriodLedgerService

_TYPES = ["All", "Gold", "Silver", "Other"]


class StockPeriodLedgerView(ctk.CTkFrame):
    TITLE = "Stock Period Ledger"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = StockPeriodLedgerService(database, gilevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.type = ctk.CTkOptionMenu(head, width=100, values=_TYPES); self.type.pack(side="left", padx=8)
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(8, 4))
        self.d1 = ctk.CTkEntry(head, width=110); self.d1.pack(side="left"); self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(8, 4))
        self.d2 = ctk.CTkEntry(head, width=110); self.d2.pack(side="left"); self.d2.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[
            ("code", "Item", 110), ("name", "Name", 180), ("opwgt", "Opening", 100),
            ("rcvdwgt", "Received", 100), ("issuedwgt", "Issued", 100), ("clwgt", "Closing", 100)], key_field="code")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _show(self):
        itype = {"Gold": "G", "Silver": "S", "Other": "O"}.get(self.type.get(), "")
        try:
            rows = self.service.ledger(self.d1.get(), self.d2.get(), itype=itype, only_with_txn=True)
            self.grid_widget.set_rows([{
                "code": r["code"], "name": r["name"], "opwgt": f'{r["opwgt"]:.3f}',
                "rcvdwgt": f'{r["rcvdwgt"]:.3f}', "issuedwgt": f'{r["issuedwgt"]:.3f}',
                "clwgt": f'{r["clwgt"]:.3f}'} for r in rows])
            self.summary.configure(text=f"{len(rows)} item(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
