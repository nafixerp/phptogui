"""Debit / Credit Note window (post)."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import DebitCreditNoteService, NoteError


class DebitCreditNoteView(ctk.CTkFrame):
    TITLE = "Debit / Credit Note"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = DebitCreditNoteService(PostingEngine(database), session)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))
        card = ctk.CTkFrame(self); card.pack(fill="x", padx=16, pady=8)
        self.stype = ctk.CTkOptionMenu(card, width=200, values=["D (Debit Note)", "C (Credit Note)"])
        self.stype.pack(anchor="w", padx=12, pady=6)
        self.tdate = self._row(card, "Date"); self.tdate.insert(0, date.today().isoformat())
        self._e = {}
        for k, lbl, zero in [("accode", "Account", False), ("adjac", "Adjustment A/c", False),
                             ("amt", "Amount", True), ("netamt", "Net Amount", True), ("taxamt", "Tax Amount", True)]:
            self._e[k] = self._row(card, lbl, zero)
        ctk.CTkButton(self, text="Post Note", width=120, command=self._post).pack(anchor="w", padx=16, pady=8)
        self.status = ctk.CTkLabel(self, text="", wraplength=520); self.status.pack(anchor="w", padx=16)

    def _row(self, parent, label, zero=False):
        row = ctk.CTkFrame(parent, fg_color="transparent"); row.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(row, text=label, width=150, anchor="w").pack(side="left")
        e = ctk.CTkEntry(row, width=240); e.pack(side="left")
        if zero: e.insert(0, "0")
        return e

    def _post(self):
        stype = self.stype.get()[0]
        try:
            res = self.service.save(stype, self._e["accode"].get(), self._e["adjac"].get(),
                                    self._e["amt"].get(), self._e["netamt"].get(), self._e["taxamt"].get(),
                                    self.tdate.get())
        except (NoteError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=f"{res['message']} — {res['vchno']} (slno {res['slno']}).", text_color="#1E8449")
