"""Sales Return window (post)."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import SalesReturnError, SalesReturnService

_F = [("billno", "Bill No"), ("custcode", "Customer A/c"), ("cbcode", "Cash/Bank A/c"),
      ("billamt", "Bill Amount"), ("staxamt", "Tax Amount"), ("discount", "Discount"),
      ("pamt", "Refund Paid")]


class SalesReturnView(ctk.CTkFrame):
    TITLE = "Sales Return"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = SalesReturnService(PostingEngine(database), session)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))
        card = ctk.CTkFrame(self); card.pack(fill="x", padx=16, pady=8)
        self.tdate = self._row(card, "Date")
        self.tdate.insert(0, date.today().isoformat())
        self._e = {}
        for k, lbl in _F:
            self._e[k] = self._row(card, lbl, k not in ("billno", "custcode", "cbcode"))
        self.is_cst = ctk.BooleanVar()
        ctk.CTkCheckBox(card, text="Interstate (IGST)", variable=self.is_cst).pack(anchor="w", padx=12, pady=4)
        ctk.CTkButton(self, text="Post Return", width=120, command=self._post).pack(anchor="w", padx=16, pady=8)
        self.status = ctk.CTkLabel(self, text="", wraplength=560); self.status.pack(anchor="w", padx=16)

    def _row(self, parent, label, zero=False):
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(row, text=label, width=150, anchor="w").pack(side="left")
        e = ctk.CTkEntry(row, width=240); e.pack(side="left")
        if zero:
            e.insert(0, "0")
        return e

    def _post(self):
        d = {k: e.get() for k, e in self._e.items()}
        d["is_cst"] = self.is_cst.get()
        try:
            res = self.service.post(0, self.tdate.get(), d)
        except (SalesReturnError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=f"Posted return slno {res['slno']} ({res['lines']} lines, balance {res['balance']}).",
                              text_color="#1E8449")
