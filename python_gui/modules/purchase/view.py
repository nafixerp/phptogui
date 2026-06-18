"""Purchase Bill window — item grid + computation -> compute -> post."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from . import calc
from .service import PurchaseError, PurchasePostingService

_ITEM_INPUTS = [("icode", "Item"), ("weight", "Weight"), ("stone_wgt", "Stone Wt"),
                ("rate", "Rate"), ("making_charge", "MC"), ("qty", "Qty")]
_CHARGES = [("supplier_code", "Supplier A/c"), ("tax_perc", "Tax %"), ("discount", "Discount"),
            ("paid_amount", "Paid"), ("chq_amount", "Cheque Amt"), ("chq_bank", "Cheque Bank")]


class PurchaseView(ctk.CTkFrame):
    TITLE = "Purchase Bill"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PurchasePostingService(PostingEngine(database), session)
        self._items: list[dict] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Date").pack(side="left", padx=(16, 4))
        self.tdate = ctk.CTkEntry(head, width=110); self.tdate.pack(side="left"); self.tdate.insert(0, date.today().isoformat())

        self.grid_widget = DataGrid(self, columns=[("icode", "Item", 90), ("weight", "Weight", 80),
                                    ("rate", "Rate", 80), ("making_charge", "MC", 70), ("amount", "Amount", 110)],
                                    key_field="icode")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)

        side = ctk.CTkScrollableFrame(self, width=280, label_text="Entry"); side.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)
        self._inp = {}
        ctk.CTkLabel(side, text="— Item —", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(4, 0))
        for key, label in _ITEM_INPUTS:
            ctk.CTkLabel(side, text=label).pack(anchor="w", padx=10)
            e = ctk.CTkEntry(side, width=180); e.pack(anchor="w", padx=10)
            if key != "icode":
                e.insert(0, "0")
            self._inp[key] = e
        ctk.CTkButton(side, text="Add Item", width=100, command=self._add).pack(anchor="w", padx=10, pady=6)

        ctk.CTkLabel(side, text="— Bill —", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(6, 0))
        self._chg = {}
        for key, label in _CHARGES:
            ctk.CTkLabel(side, text=label).pack(anchor="w", padx=10)
            e = ctk.CTkEntry(side, width=180); e.pack(anchor="w", padx=10)
            if key not in ("supplier_code", "chq_bank"):
                e.insert(0, "0")
            self._chg[key] = e
        self.interstate = ctk.BooleanVar()
        ctk.CTkCheckBox(side, text="Interstate (IGST)", variable=self.interstate).pack(anchor="w", padx=10, pady=4)
        ctk.CTkButton(side, text="Compute & Post", width=180, command=self._post).pack(anchor="w", padx=10, pady=6)
        self.status = ctk.CTkLabel(side, text="", wraplength=250); self.status.pack(anchor="w", padx=10)

    def _add(self):
        item = {k: self._inp[k].get() for k in self._inp}
        item["amount"] = str(calc.line_amount(item))
        self._items.append(item)
        self.grid_widget.set_rows(self._items)
        for k, e in self._inp.items():
            if k != "icode":
                e.delete(0, "end"); e.insert(0, "0")

    def _post(self):
        if not self._items:
            self.status.configure(text="Add at least one item.", text_color="#C0392B"); return
        extra = {k: e.get() for k, e in self._chg.items()}
        extra["interstate"] = self.interstate.get()
        amounts = calc.compute(self._items, extra)
        try:
            res = self.service.post(0, self.tdate.get(), amounts)
        except (PurchaseError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(
            text=f"Bill {amounts['bill_total']:.2f} Tax {amounts['tax']:.2f} Net {amounts['net_total']:.2f}\n"
                 f"Posted slno {res['slno']} ({res['lines']} lines, balanced).", text_color="#1E8449")
        self._items = []; self.grid_widget.set_rows([])
