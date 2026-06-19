"""Repair Return window — return repaired items to the customer."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from .service import RepairReturnError, RepairReturnService

_ITEM_FIELDS = [("itemcode", "Item"), ("qty", "Qty"), ("weight", "Weight"),
                ("stonewgt", "Stone"), ("netwgt", "Net Wt"), ("mcharge", "MC"),
                ("amount", "Amount"), ("stktype", "Stk Type")]


class RepairReturnView(ctk.CTkFrame):
    TITLE = "Repair Return"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = RepairReturnService(PostingEngine(database), session, control=getattr(session, "gilevel", 1))
        self._items: list[dict] = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(3, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="Save Bill", width=110, command=self._save).pack(side="right", padx=6)
        hdr = ctk.CTkFrame(self, fg_color="transparent"); hdr.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        self.header: dict[str, ctk.CTkEntry] = {}
        for key, label, dflt in [("custcode", "Cust Code", ""), ("custname", "Customer", ""),
                                 ("sman", "Salesman", ""), ("amount", "Amount", "0"),
                                 ("taxamt", "Tax Amt", "0"), ("discount", "Discount", "0"),
                                 ("rcvd", "Received", "0"), ("cashbank_code", "Cash/Bank", "CASH")]:
            ctk.CTkLabel(hdr, text=label).pack(side="left", padx=(6, 2))
            e = ctk.CTkEntry(hdr, width=90); e.pack(side="left")
            if dflt:
                e.insert(0, dflt)
            self.header[key] = e
        entry = ctk.CTkFrame(self, fg_color="transparent"); entry.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        self.inputs: dict[str, ctk.CTkEntry] = {}
        for key, label in _ITEM_FIELDS:
            ctk.CTkLabel(entry, text=label).pack(side="left", padx=(6, 2))
            e = ctk.CTkEntry(entry, width=80); e.pack(side="left"); self.inputs[key] = e
        ctk.CTkButton(entry, text="Add Item", width=80, command=self._add).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=[(k, lbl, 90) for k, lbl in _ITEM_FIELDS], key_field="itemcode")
        self.grid_widget.grid(row=3, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=4, column=0, sticky="ew", padx=14, pady=4)

    def _add(self):
        row = {k: (e.get() or "").strip() for k, e in self.inputs.items()}
        if not row.get("itemcode"):
            self.status.configure(text="Item code required.", text_color="#C0392B"); return
        self._items.append(row); self.grid_widget.set_rows(self._items)
        for e in self.inputs.values():
            e.delete(0, "end")

    def _save(self):
        header = {k: e.get() for k, e in self.header.items()}
        header["tdate"] = date.today().isoformat()
        try:
            res = self.service.save(header, self._items)
        except (RepairReturnError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._items = []; self.grid_widget.set_rows([])
        bal = "balanced" if res["balanced"] else "UNBALANCED"
        self.status.configure(text=f'Saved {res["bill_no"]} (slno {res["slno"]}, {bal})', text_color="#1E8449")
