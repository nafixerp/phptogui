"""Order Bill window (header + advance posting)."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import OrderError, OrderService

_FIELDS = [("custcode", "Customer A/c"), ("custname", "Customer Name"),
           ("duedate", "Due Date"), ("rate", "Rate"), ("billamt", "Bill Amount"),
           ("advance", "Advance"), ("refund", "Refund"), ("cbcode", "Cash/Bank A/c"),
           ("ccamt", "Card Amt"), ("chqamt", "Cheque Amt"), ("note", "Note")]


class OrderBillView(ctk.CTkFrame):
    TITLE = "Order Bill"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = OrderService(PostingEngine(database), session)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 8))
        card = ctk.CTkScrollableFrame(self, height=360); card.pack(fill="both", expand=True, padx=16, pady=8)
        self._e: dict[str, ctk.CTkEntry] = {}
        self.tdate = self._row(card, "Date (YYYY-MM-DD)")
        self.tdate.insert(0, date.today().isoformat())
        for key, label in _FIELDS:
            self._e[key] = self._row(card, label, key not in ("custcode", "custname", "cbcode", "note", "duedate"))

        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(anchor="w", padx=16, pady=8)
        ctk.CTkButton(bar, text="Save Order", width=120, command=self._save).pack(side="left")
        self.status = ctk.CTkLabel(self, text="", wraplength=560); self.status.pack(anchor="w", padx=16)

    def _row(self, parent, label, zero=False):
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(row, text=label, width=160, anchor="w").pack(side="left")
        e = ctk.CTkEntry(row, width=240); e.pack(side="left")
        if zero:
            e.insert(0, "0")
        return e

    def _save(self):
        header = {k: e.get() for k, e in self._e.items()}
        header["tdate"] = self.tdate.get()
        try:
            res = self.service.save(header)
        except (OrderError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(
            text=f"Order #{res['ordno']} saved (slno {res['slno']}, {res['advance_lines']} advance lines).",
            text_color="#1E8449")
