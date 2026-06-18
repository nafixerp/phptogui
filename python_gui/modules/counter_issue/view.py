"""Counter Issue window — stock currently on a counter."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import CounterIssueService


class CounterIssueView(ctk.CTkFrame):
    TITLE = "Counter Issue"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = CounterIssueService(database)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Counter").pack(side="left", padx=(16, 4))
        counters = [c["code"] for c in self.service.counters()] or [""]
        self.counter = ctk.CTkOptionMenu(head, width=130, values=counters, command=lambda _v: self._show()); self.counter.pack(side="left", padx=6)
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[
            ("bcode", "Barcode", 100), ("icode", "Item", 100), ("itemname", "Name", 180),
            ("qty", "Qty", 60), ("weight", "Wt", 90), ("netwgt", "Net Wt", 100),
            ("stk", "Stk", 50), ("rate", "Rate", 90)], key_field="bcode")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._show()

    def _show(self):
        try:
            res = self.service.by_counter(self.counter.get())
            self.grid_widget.set_rows([{
                "bcode": r["bcode"], "icode": r["icode"], "itemname": r["itemname"], "qty": r["qty"],
                "weight": f'{r["weight"]:.3f}', "netwgt": f'{r["netwgt"]:.3f}', "stk": r["stk"],
                "rate": f'{r["rate"]:.2f}'} for r in res["rows"]])
            self.summary.configure(text=f'{res["counterName"]}: {len(res["rows"])} item(s).', text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
