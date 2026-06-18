"""Item Adjustment window (from -> to weight transfer)."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .repo import ItemAdjustmentRepo
from .service import ItemAdjustmentError, ItemAdjustmentService


class ItemAdjustmentView(ctk.CTkFrame):
    TITLE = "Item Stock Adjustment"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = ItemAdjustmentService(ItemAdjustmentRepo(database), PostingEngine(database), session)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))
        card = ctk.CTkFrame(self); card.pack(fill="x", padx=16, pady=8)
        self.tdate = self._row(card, "Date"); self.tdate.insert(0, date.today().isoformat())
        self._e = {}
        for k, lbl, zero in [("fromcode", "From Item", False), ("fromwgt", "From Weight", True),
                             ("fromstktype", "From Stock Type", False), ("tocode", "To Item", False),
                             ("towgt", "To Weight", True), ("tostktype", "To Stock Type", False),
                             ("particular", "Particular", False)]:
            self._e[k] = self._row(card, lbl, zero)
        ctk.CTkButton(self, text="Save Adjustment", width=140, command=self._save).pack(anchor="w", padx=16, pady=8)
        self.status = ctk.CTkLabel(self, text="", wraplength=560); self.status.pack(anchor="w", padx=16)

    def _row(self, parent, label, zero=False):
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(row, text=label, width=150, anchor="w").pack(side="left")
        e = ctk.CTkEntry(row, width=240); e.pack(side="left")
        if zero:
            e.insert(0, "0")
        return e

    def _save(self):
        data = {k: e.get() for k, e in self._e.items()}
        data["tdate"] = self.tdate.get()
        try:
            res = self.service.save(data)
        except (ItemAdjustmentError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=f"{res['message']} (slno {res['slno']}).", text_color="#1E8449")
