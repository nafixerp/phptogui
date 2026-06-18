"""Stock Register window (read-only)."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import StockRegisterService


class StockRegisterView(ctk.CTkFrame):
    TITLE = "Stock Register"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = StockRegisterService(database, rlevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(16, 4))
        self.d1 = ctk.CTkEntry(head, width=110); self.d1.pack(side="left")
        self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(12, 4))
        self.d2 = ctk.CTkEntry(head, width=110); self.d2.pack(side="left")
        self.d2.insert(0, date.today().isoformat())
        ctk.CTkLabel(head, text="Type").pack(side="left", padx=(12, 4))
        self.itype = ctk.CTkEntry(head, width=60); self.itype.pack(side="left")
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)

        self.summary = ctk.CTkLabel(self, text="", anchor="w")
        self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("code", "Item", 90), ("name", "Name", 180),
                                    ("op_weight", "Op Wt", 90), ("purchased_weight", "Purch", 90),
                                    ("salesd_weight", "Sales", 90), ("close_weight", "Close Wt", 100)],
                                    key_field="code")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _show(self):
        try:
            rows = self.service.summary(self.d1.get(), self.d2.get(), self.itype.get().strip().upper())
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        disp = [{"code": r["code"], "name": r["name"],
                 "op_weight": f'{r["op_weight"]:.3f}', "purchased_weight": f'{r["purchased_weight"]:.3f}',
                 "salesd_weight": f'{r["salesd_weight"]:.3f}', "close_weight": f'{r["close_weight"]:.3f}'}
                for r in rows]
        self.grid_widget.set_rows(disp)
        self.summary.configure(text=f"Items with stock/movement: {len(disp)}", text_color=("gray20", "gray80"))
