"""e-Invoice Register window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import EInvoiceRegisterService

_STATUS = ["All", "generated", "cancelled", "failed"]


class EInvoiceRegisterView(ctk.CTkFrame):
    TITLE = "e-Invoice Register"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = EInvoiceRegisterService(database)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(16, 4))
        self.d1 = ctk.CTkEntry(head, width=110); self.d1.pack(side="left"); self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(8, 4))
        self.d2 = ctk.CTkEntry(head, width=110); self.d2.pack(side="left"); self.d2.insert(0, date.today().isoformat())
        self.status_f = ctk.CTkOptionMenu(head, width=110, values=_STATUS); self.status_f.pack(side="left", padx=8)
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[
            ("bill_no", "Bill No", 110), ("bill_date", "Date", 100), ("customer_name", "Customer", 170),
            ("net_total", "Net Total", 120), ("status", "Status", 90), ("irn", "IRN", 200)], key_field="id")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._show()

    def _show(self):
        st = self.status_f.get(); st = "" if st == "All" else st
        try:
            rows = self.service.register(self.d1.get(), self.d2.get(), status=st)
            self.grid_widget.set_rows([{
                "id": r.get("id"), "bill_no": str(r.get("bill_no") or ""), "bill_date": str(r.get("bill_date") or ""),
                "customer_name": str(r.get("customer_name") or ""), "net_total": f'{r["net_total"]:.2f}',
                "status": str(r.get("status") or ""), "irn": str(r.get("irn") or "")} for r in rows])
            self.summary.configure(text=f"{len(rows)} invoice(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
