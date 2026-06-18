"""Party Outstanding window — supplier payable / customer receivable."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import PartyOutstandingService

_TYPES = ["Supplier", "Customer"]


class PartyOutstandingView(ctk.CTkFrame):
    TITLE = "Party Outstanding"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PartyOutstandingService(database, gilevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.type = ctk.CTkOptionMenu(head, width=120, values=_TYPES, command=lambda _v: self._show()); self.type.pack(side="left", padx=10)
        ctk.CTkLabel(head, text="As on").pack(side="left", padx=(8, 4))
        self.asof = ctk.CTkEntry(head, width=110); self.asof.pack(side="left"); self.asof.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("accode", "Code", 110), ("cname", "Party", 200), ("mobile", "Mobile", 120),
                                    ("status", "Type", 70), ("bal_abs", "Balance", 130)], key_field="accode")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._show()

    def _show(self):
        try:
            res = self.service.outstanding(self.type.get(), self.asof.get())
            self.grid_widget.set_rows([{"accode": r["accode"], "cname": r["cname"], "mobile": r["mobile"],
                                        "status": r["status"], "bal_abs": f'{r["bal_abs"]:.2f}'} for r in res["rows"]])
            t = res["totals"]
            self.summary.configure(text=f'{t["count"]} party(s)  ·  Receivable {t["tr"]:.2f}  ·  Payable {t["tg"]:.2f}',
                                   text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
