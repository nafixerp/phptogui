"""Order Advance-After window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import OrderAdvanceAfterError, OrderAdvanceAfterService


class OrderAdvanceAfterView(ctk.CTkFrame):
    TITLE = "Order Advance-After"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = OrderAdvanceAfterService(PostingEngine(database), session)
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        self.fields: dict[str, ctk.CTkEntry] = {}
        for i, (key, label, dflt) in enumerate([("ordno", "Order No", ""), ("amount", "Amount", "0"),
                                                ("rate", "Rate", "0"), ("cashbank_code", "Cash/Bank", "CASH")], start=1):
            ctk.CTkLabel(self, text=label).grid(row=i, column=0, sticky="w", padx=12, pady=4)
            e = ctk.CTkEntry(self, width=200); e.grid(row=i, column=1, sticky="w", padx=12, pady=4)
            if dflt:
                e.insert(0, dflt)
            self.fields[key] = e
        ctk.CTkButton(self, text="Save Advance", width=130, command=self._save).grid(row=5, column=1, sticky="w", padx=12, pady=10)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=6, column=0, columnspan=2, sticky="ew", padx=14, pady=4)

    def _save(self):
        f = {k: e.get() for k, e in self.fields.items()}
        try:
            res = self.service.save(ordno=f["ordno"], tdate=date.today().isoformat(), amount=f["amount"] or 0,
                                    rate=f["rate"] or 0, cashbank_code=f["cashbank_code"])
        except (OrderAdvanceAfterError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=f'Saved {res["vchno"]} (slno {res["slno"]})', text_color="#1E8449")
