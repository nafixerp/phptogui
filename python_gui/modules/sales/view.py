"""Sales posting window (simplified bill -> daybook).

Captures the principal bill amounts and posts the standard sales heads
(RS/customer/cash/tax/discount/EP) with ROUND balancing. The full item-grid
sales entry with per-line tax computation is a larger follow-on; this posts a
balanced sales voucher to the ledger from the entered totals.
"""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import SalesError, SalesPostingService

_FIELDS = [
    ("customer_code", "Customer A/c"), ("cashbank_code", "Cash/Bank A/c"),
    ("bill_total", "Bill Total"), ("net_total", "Net Total"), ("discount", "Discount"),
    ("tax", "Tax (total)"), ("sgst", "SGST"), ("cgst", "CGST"), ("igst", "IGST"),
    ("exchange_amount", "Exchange (old gold)"), ("received", "Received"),
]


class SalesView(ctk.CTkFrame):
    TITLE = "Sales Bill (post)"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = SalesPostingService(PostingEngine(database), session)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 8))
        card = ctk.CTkScrollableFrame(self, height=380); card.pack(fill="both", expand=True, padx=16, pady=8)
        self._e: dict[str, ctk.CTkEntry] = {}
        self.tdate = self._row(card, "tdate", "Date (YYYY-MM-DD)")
        self.tdate.insert(0, date.today().isoformat())
        for key, label in _FIELDS:
            self._e[key] = self._row(card, key, label)
        self.is_cst = ctk.BooleanVar()
        ctk.CTkCheckBox(card, text="Interstate (IGST)", variable=self.is_cst).pack(anchor="w", padx=12, pady=4)

        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(anchor="w", padx=16, pady=8)
        ctk.CTkButton(bar, text="Post Sale", width=110, command=self._post).pack(side="left")
        self.status = ctk.CTkLabel(self, text="", wraplength=560); self.status.pack(anchor="w", padx=16)

    def _row(self, parent, key, label):
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(row, text=label, width=180, anchor="w").pack(side="left")
        e = ctk.CTkEntry(row, width=240); e.pack(side="left")
        if key not in ("customer_code", "cashbank_code"):
            e.insert(0, "0")
        return e

    def _post(self):
        amounts = {k: e.get() for k, e in self._e.items()}
        amounts["is_cst"] = self.is_cst.get()
        try:
            res = self.service.post(0, self.tdate.get(), amounts)
        except (SalesError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=f"Posted sale slno {res['slno']} ({res['lines']} lines, balanced).",
                              text_color="#1E8449")
