"""Party bill-wise Receipt / Payment windows."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from .service import PartyBillwiseError, PartyBillwiseService

_FIELDS = [("slno", "Bill Slno"), ("billno", "Bill No"), ("balance", "Balance"),
           ("alocamt", "Allocate"), ("discamt", "Discount")]


class _BillwiseBase(ctk.CTkFrame):
    MODE = "receipt"
    TITLE = "Bill-wise"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PartyBillwiseService(PostingEngine(database), self.MODE, session, control=getattr(session, "gilevel", 1))
        self._items: list[dict] = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Party").pack(side="left", padx=(16, 4))
        self.party = ctk.CTkEntry(head, width=110); self.party.pack(side="left")
        ctk.CTkLabel(head, text="Cash/Bank").pack(side="left", padx=(8, 4))
        self.cbcode = ctk.CTkEntry(head, width=90); self.cbcode.pack(side="left"); self.cbcode.insert(0, "CASH")
        ctk.CTkButton(head, text="Save", width=90, command=self._save).pack(side="right", padx=6)
        entry = ctk.CTkFrame(self, fg_color="transparent"); entry.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        self.inputs: dict[str, ctk.CTkEntry] = {}
        for key, label in _FIELDS:
            ctk.CTkLabel(entry, text=label).pack(side="left", padx=(6, 2))
            e = ctk.CTkEntry(entry, width=90); e.pack(side="left"); self.inputs[key] = e
        ctk.CTkButton(entry, text="Add Bill", width=80, command=self._add).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=[(k, lbl, 100) for k, lbl in _FIELDS], key_field="billno")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=3, column=0, sticky="ew", padx=14, pady=4)

    def _add(self):
        row = {k: (e.get() or "").strip() for k, e in self.inputs.items()}
        row["selected"] = True
        if not row.get("billno"):
            self.status.configure(text="Bill no required.", text_color="#C0392B"); return
        self._items.append(row); self.grid_widget.set_rows(self._items)
        for e in self.inputs.values():
            e.delete(0, "end")

    def _save(self):
        if not self._items:
            self.status.configure(text="No bills allocated.", text_color="#C0392B"); return
        try:
            res = self.service.post(partycode=self.party.get(), tdate=date.today().isoformat(),
                                    items=self._items, cbcode=self.cbcode.get())
        except (PartyBillwiseError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._items = []; self.grid_widget.set_rows([])
        if not res.get("saved"):
            self.status.configure(text="Nothing to save.", text_color="#C0392B"); return
        self.status.configure(text=f'Saved {res["vchno"]} (slno {res["slno"]})', text_color="#1E8449")


class CustomerBillwiseReceiptView(_BillwiseBase):
    MODE = "receipt"
    TITLE = "Customer Bill-wise Receipt"


class SupplierBillwisePaymentView(_BillwiseBase):
    MODE = "payment"
    TITLE = "Supplier Bill-wise Payment"
