"""Purchase Reports window (net / monthly / supplier-wise / check list)."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import PurchaseReportsService

_MODES = ["Net Purchase", "Monthly", "Supplier-wise", "Check List"]


class PurchaseReportsView(ctk.CTkFrame):
    TITLE = "Purchase Reports"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PurchaseReportsService(database, rlevel=getattr(session, "gilevel", 1))
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
        m = self.mode.get()
        try:
            if m == "Net Purchase":
                res = self.service.purchase_book(self.d1.get(), self.d2.get())
                self._set_cols([("k", "Measure", 200), ("v", "Amount", 200)])
                rows = [{"k": "Bills", "v": str(res["count"])}] + [{"k": k, "v": f"{v:.2f}"} for k, v in res["totals"].items()]
                self.grid_widget.set_rows(rows); self.summary.configure(text=f"{res['count']} bill(s).", text_color=("gray20", "gray80"))
            elif m == "Monthly":
                rows = self.service.monthly_purchase(self.d1.get(), self.d2.get())
                self._set_cols([("month", "Month", 120), ("count", "Bills", 80), ("billamt", "Bill Amt", 130), ("netamt", "Net Amt", 130)])
                self.grid_widget.set_rows([{"month": r["month"], "count": r["count"], "billamt": f'{r.get("billamt", 0):.2f}', "netamt": f'{r.get("netamt", 0):.2f}'} for r in rows])
                self.summary.configure(text=f"{len(rows)} month(s).", text_color=("gray20", "gray80"))
            elif m == "Supplier-wise":
                rows = self.service.supplier_wise(self.d1.get(), self.d2.get())
                self._set_cols([("suppcode", "Supplier", 120), ("name", "Name", 180), ("count", "Bills", 80), ("netamt", "Net Amt", 140)])
                self.grid_widget.set_rows([{"suppcode": r["suppcode"], "name": r.get("name", ""), "count": r["count"], "netamt": f'{r.get("netamt", 0):.2f}'} for r in rows])
                self.summary.configure(text=f"{len(rows)} supplier(s).", text_color=("gray20", "gray80"))
            else:
                rows = self.service.check_list(self.d1.get(), self.d2.get())
                self._set_cols([("billno", "Bill No", 110), ("tdate", "Date", 100), ("name", "Supplier", 200), ("netamt", "Net Amt", 120)])
                self.grid_widget.set_rows([{"billno": str(r.get("billno") or ""), "tdate": str(r.get("tdate") or ""), "name": str(r.get("name") or ""), "netamt": f'{float(r.get("netamt") or 0):.2f}'} for r in rows])
                self.summary.configure(text=f"{len(rows)} bill(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
