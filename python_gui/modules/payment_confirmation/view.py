"""Payment Confirmation window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import PaymentConfirmationError, PaymentConfirmationService


class PaymentConfirmationView(ctk.CTkFrame):
    TITLE = "Payment Confirmation"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PaymentConfirmationService(database, session, control=getattr(session, "gilevel", 1))
        self._sel = None
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="Reload", width=70, command=self._reload).pack(side="left", padx=8)
        ctk.CTkButton(head, text="Confirm Selected", width=140, command=self._confirm).pack(side="right", padx=6)
        self.grid_widget = DataGrid(self, columns=[("vchno", "Voucher", 110), ("tdate", "Date", 100), ("accode", "Account", 120),
                                    ("amount", "Amount", 120), ("particular", "Particular", 220)],
                                    on_select=self._on_select, key_field="slno")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=4)
        self._reload()

    def _reload(self):
        try:
            rows = self.service.pending()
            self.grid_widget.set_rows([{"slno": r["slno"], "vchno": r["vchno"], "tdate": r["tdate"], "accode": r["accode"],
                                        "amount": f'{r["amount"]:.2f}', "particular": r["particular"]} for r in rows])
            self.status.configure(text=f"{len(rows)} pending.", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        self._sel = row

    def _confirm(self):
        if not self._sel:
            self.status.configure(text="Select an entry.", text_color="#C0392B"); return
        try:
            msg = self.service.confirm(self._sel.get("slno"), self._sel.get("vchno", ""))
        except (PaymentConfirmationError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text=msg, text_color="#1E8449")
