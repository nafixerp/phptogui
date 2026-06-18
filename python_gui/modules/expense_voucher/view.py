"""Expense Voucher window (post)."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import ExpenseError, ExpenseVoucherService


class ExpenseVoucherView(ctk.CTkFrame):
    TITLE = "Expense Voucher Entry"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = ExpenseVoucherService(PostingEngine(database), session)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))
        card = ctk.CTkScrollableFrame(self, height=360); card.pack(fill="both", expand=True, padx=16, pady=8)
        self.tdate = self._row(card, "Date"); self.tdate.insert(0, date.today().isoformat())
        self._e = {}
        for k, lbl, dflt in [("pamtAc", "Expense A/c", "EP"), ("taxAc", "Tax A/c", "ETAX"),
                             ("discAc", "Discount A/c", "PDISC"), ("cbAc", "Cash/Bank A/c", "CASH"),
                             ("partyCode", "Party A/c", ""), ("bamt", "Bill Amount", "0"),
                             ("taxamt", "Tax Amount", "0"), ("discount", "Discount", "0"),
                             ("netamt", "Net Amount", "0"), ("paidamt", "Paid Amount", "0")]:
            e = self._row(card, lbl); e.insert(0, dflt); self._e[k] = e
        ctk.CTkButton(self, text="Post Voucher", width=130, command=self._post).pack(anchor="w", padx=16, pady=8)
        self.status = ctk.CTkLabel(self, text="", wraplength=520); self.status.pack(anchor="w", padx=16)

    def _row(self, parent, label):
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(row, text=label, width=150, anchor="w").pack(side="left")
        e = ctk.CTkEntry(row, width=240); e.pack(side="left"); return e

    def _post(self):
        d = {k: e.get() for k, e in self._e.items()}
        try:
            res = self.service.save(d, self.tdate.get())
        except (ExpenseError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=f"{res['message']} — {res['vchno']} ({res['lines']} lines, balanced).", text_color="#1E8449")
