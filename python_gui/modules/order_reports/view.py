"""Order Reports window — Process (pending) and Returns."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import OrderReportsService

_MODES = ["Pending Process", "Returns"]


class OrderReportsView(ctk.CTkFrame):
    TITLE = "Order Reports"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = OrderReportsService(database, gilevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.mode = ctk.CTkOptionMenu(head, width=150, values=_MODES, command=lambda _v: self._show()); self.mode.pack(side="left", padx=10)
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(8, 4))
        self.d1 = ctk.CTkEntry(head, width=110); self.d1.pack(side="left"); self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(8, 4))
        self.d2 = ctk.CTkEntry(head, width=110); self.d2.pack(side="left"); self.d2.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("a", "", 100)], key_field="a"); self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._show()

    def _set_cols(self, cols):
        self.grid_widget.destroy()
        self.grid_widget = DataGrid(self, columns=cols, key_field=cols[0][0]); self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _show(self):
        try:
            if self.mode.get() == "Pending Process":
                rows = self.service.pending_process()
                self._set_cols([("ordno", "Order No", 120), ("tdate", "Date", 100), ("custname", "Customer", 180),
                                ("billamt", "Bill Amt", 110), ("tadv", "Advance", 110), ("mobile", "Mobile", 120)])
                self.grid_widget.set_rows([{"ordno": r["ordno"], "tdate": r["tdate"], "custname": r["custname"],
                                            "billamt": f'{r["billamt"]:.2f}', "tadv": f'{r["tadv"]:.2f}', "mobile": r["mobile"]} for r in rows])
            else:
                rows = self.service.returns(self.d1.get(), self.d2.get())
                self._set_cols([("ordno", "Order No", 120), ("custname", "Customer", 180), ("salebill", "Sale Bill", 110),
                                ("sale_tdate", "Sale Date", 100), ("sale_billamt", "Sale Amt", 120)])
                self.grid_widget.set_rows([{"ordno": str(r.get("ordno") or ""), "custname": str(r.get("custname") or ""),
                                            "salebill": str(r.get("salebill") or ""), "sale_tdate": str(r.get("sale_tdate") or ""),
                                            "sale_billamt": f'{float(r.get("sale_billamt") or 0):.2f}'} for r in rows])
            self.summary.configure(text=f"{len(rows)} row(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
