"""Receipt voucher window."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import ReceiptError, ReceiptService


class ReceiptView(ctk.CTkFrame):
    TITLE = "Receipt"
    _DISCOUNT = True

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = self._make_service(database, session)
        self._slno = 0

        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 8))
        card = ctk.CTkFrame(self); card.pack(fill="x", padx=16, pady=8)
        self._e: dict[str, ctk.CTkEntry] = {}
        fields = [("tdate", "Date (YYYY-MM-DD)"), ("cbcode", "Cash/Bank A/c"),
                  ("accode", "Party A/c"), ("amount", "Amount")]
        if self._DISCOUNT:
            fields.append(("discount", "Discount"))
        fields += [("chequeno", "Cheque No"), ("particular", "Particulars")]
        for key, label in fields:
            row = ctk.CTkFrame(card, fg_color="transparent"); row.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(row, text=label, width=160, anchor="w").pack(side="left")
            e = ctk.CTkEntry(row, width=280); e.pack(side="left"); self._e[key] = e
        self._e["tdate"].insert(0, date.today().isoformat())
        if self._DISCOUNT:
            self._e["discount"].insert(0, "0")

        self.pdc = ctk.BooleanVar()
        ctk.CTkCheckBox(card, text="PDC (post-dated cheque)", variable=self.pdc).pack(anchor="w", padx=12, pady=4)

        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(anchor="w", padx=16, pady=8)
        ctk.CTkButton(bar, text="New", width=80, command=self._new).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="Save", width=80, command=self._save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="Delete", width=80, fg_color="#B03A2E", hover_color="#943126",
                      command=self._delete).pack(side="left")
        self.status = ctk.CTkLabel(self, text="", wraplength=560); self.status.pack(anchor="w", padx=16)

    def _make_service(self, database, session):
        return ReceiptService(PostingEngine(database), session)

    def _form(self):
        f = {k: e.get() for k, e in self._e.items()}
        f["pdc"] = self.pdc.get()
        f["slno"] = self._slno
        return f

    def _new(self):
        for k, e in self._e.items():
            e.delete(0, "end")
        self._e["tdate"].insert(0, date.today().isoformat())
        if self._DISCOUNT:
            self._e["discount"].insert(0, "0")
        self.pdc.set(False); self._slno = 0
        self.status.configure(text="New voucher", text_color=("gray30", "gray70"))

    def _save(self):
        try:
            res = self.service.save(self._form(), "A")
        except (ReceiptError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._slno = res["slno"]
        self.status.configure(text=f"{res['message']} — {res['vchno']} (slno {res['slno']})",
                              text_color="#1E8449")

    def _delete(self):
        if self._slno <= 0:
            self.status.configure(text="Save or load a voucher first.", text_color="#C0392B"); return
        try:
            msg = self.service.delete(self._slno)
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._new(); self.status.configure(text=msg, text_color="#1E8449")
