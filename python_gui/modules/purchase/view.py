"""Purchase posting window (simplified bill -> daybook)."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import PurchaseError, PurchasePostingService

_FIELDS = [
    ("supplier_code", "Supplier A/c"), ("bill_total", "Bill Total"), ("net_total", "Net Total"),
    ("paid_amount", "Paid"), ("chq_amount", "Cheque Amt"), ("chq_bank", "Cheque Bank A/c"),
    ("discount", "Discount"), ("tax", "Tax"), ("cess", "Cess"), ("hallmark_charge", "Hallmark"),
    ("tcs_amt", "TCS"), ("others", "Others"), ("exchange_amount", "Exchange"), ("round_amt", "Round-off"),
]


class PurchaseView(ctk.CTkFrame):
    TITLE = "Purchase Bill (post)"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PurchasePostingService(PostingEngine(database), session)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 8))
        card = ctk.CTkScrollableFrame(self, height=400); card.pack(fill="both", expand=True, padx=16, pady=8)
        self._e: dict[str, ctk.CTkEntry] = {}
        self.tdate = self._row(card, "tdate", "Date (YYYY-MM-DD)")
        self.tdate.insert(0, date.today().isoformat())
        for key, label in _FIELDS:
            self._e[key] = self._row(card, key, label)
        self.interstate = ctk.BooleanVar()
        ctk.CTkCheckBox(card, text="Interstate (IGST)", variable=self.interstate).pack(anchor="w", padx=12, pady=2)
        self.tax_ext = ctk.BooleanVar()
        ctk.CTkCheckBox(card, text="Tax external (PTAXEXP)", variable=self.tax_ext).pack(anchor="w", padx=12, pady=2)

        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(anchor="w", padx=16, pady=8)
        ctk.CTkButton(bar, text="Post Purchase", width=130, command=self._post).pack(side="left")
        self.status = ctk.CTkLabel(self, text="", wraplength=560); self.status.pack(anchor="w", padx=16)

    def _row(self, parent, key, label):
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(row, text=label, width=180, anchor="w").pack(side="left")
        e = ctk.CTkEntry(row, width=240); e.pack(side="left")
        if key not in ("supplier_code", "chq_bank"):
            e.insert(0, "0")
        return e

    def _post(self):
        amounts = {k: e.get() for k, e in self._e.items()}
        amounts["interstate"] = self.interstate.get()
        amounts["tax_ext"] = self.tax_ext.get()
        try:
            res = self.service.post(0, self.tdate.get(), amounts)
        except (PurchaseError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=f"Posted purchase slno {res['slno']} ({res['lines']} lines, balanced).",
                              text_color="#1E8449")
