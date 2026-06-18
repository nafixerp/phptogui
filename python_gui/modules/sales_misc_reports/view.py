"""Sales Misc Reports window — Delivery Status / VA Check List."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import SalesMiscReportsService

_MODES = ["Delivery Status", "VA Check List"]
_REPTYPE = {"All": "", "Delivered": "delivered", "Locker": "locker", "Anamath": "anamath", "Pending": "pending"}


class SalesMiscReportsView(ctk.CTkFrame):
    TITLE = "Sales Misc Reports"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = SalesMiscReportsService(database, rlevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.mode = ctk.CTkOptionMenu(head, width=160, values=_MODES, command=lambda _v: self._show()); self.mode.pack(side="left", padx=10)
        self.reptype = ctk.CTkOptionMenu(head, width=110, values=list(_REPTYPE)); self.reptype.pack(side="left", padx=4)
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
            if self.mode.get() == "Delivery Status":
                rows = self.service.delivery_status(self.d1.get(), self.d2.get(), _REPTYPE[self.reptype.get()])
                self._set_cols([("billno", "Bill", 100), ("tdate", "Date", 100), ("custname", "Customer", 180),
                                ("dstatus", "Status", 70), ("goldwgt", "Gold Wt", 100), ("balance", "Balance", 120)])
                self.grid_widget.set_rows([{"billno": str(r.get("billno") or ""), "tdate": r["tdate"], "custname": r["custname"],
                                            "dstatus": r["dstatus"], "goldwgt": f'{r["goldwgt"]:.3f}', "balance": f'{r["balance"]:.2f}'} for r in rows])
                self.summary.configure(text=f"{len(rows)} bill(s).", text_color=("gray20", "gray80"))
            else:
                v = self.service.va_check(self.d1.get(), self.d2.get())
                self._set_cols([("k", "Measure", 220), ("val", "Value", 200)])
                self.grid_widget.set_rows([
                    {"k": "Weight", "val": f'{v["weight"]:.3f}'},
                    {"k": "Wastage", "val": f'{v["wastage"]:.3f}'},
                    {"k": "Making Charge", "val": f'{v["mcharge"]:.2f}'},
                    {"k": "VA Amount", "val": f'{v["vaamt"]:.2f}'},
                    {"k": "Stone Price", "val": f'{v["stoneprice"]:.2f}'},
                    {"k": "Discount", "val": f'{v["disc"]:.2f}'},
                    {"k": "Avg VA %", "val": f'{v["tvaperc"]:.2f}'},
                ])
                self.summary.configure(text=f'VA amount {v["vaamt"]:.2f}', text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
