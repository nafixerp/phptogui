"""Refinery Bill (issue) window — bulk metal issue to a refiner."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from .service import RefineryBillError, RefineryBillService

_FIELDS = [("item_code", "Item"), ("qty", "Qty"), ("weight", "Weight"), ("stone_wgt", "Stone"),
           ("test_pcs", "Test Pcs"), ("touch", "Touch"), ("stktype", "Stk Type")]


class RefineryBillView(ctk.CTkFrame):
    TITLE = "Refinery Bill (Issue)"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = RefineryBillService(PostingEngine(database), session)
        self._rows: list[dict] = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Refiner").pack(side="left", padx=(16, 4))
        self.refcode = ctk.CTkEntry(head, width=110); self.refcode.pack(side="left")
        ctk.CTkLabel(head, text="Date").pack(side="left", padx=(8, 4))
        self.tdate = ctk.CTkEntry(head, width=110); self.tdate.pack(side="left"); self.tdate.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Save Bill", width=100, command=self._save).pack(side="right", padx=6)
        entry = ctk.CTkFrame(self, fg_color="transparent"); entry.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        self.inputs: dict[str, ctk.CTkEntry] = {}
        for key, label in _FIELDS:
            ctk.CTkLabel(entry, text=label).pack(side="left", padx=(6, 2))
            e = ctk.CTkEntry(entry, width=80); e.pack(side="left"); self.inputs[key] = e
        ctk.CTkButton(entry, text="Add", width=60, command=self._add).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=[(k, lbl, 90) for k, lbl in _FIELDS], key_field="item_code")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=3, column=0, sticky="ew", padx=14, pady=4)

    def _add(self):
        row = {k: (e.get() or "").strip() for k, e in self.inputs.items()}
        if not row.get("item_code"):
            self.status.configure(text="Item code required.", text_color="#C0392B"); return
        self._rows.append(row); self.grid_widget.set_rows(self._rows)
        for e in self.inputs.values():
            e.delete(0, "end")

    def _save(self):
        if not self._rows:
            self.status.configure(text="No items.", text_color="#C0392B"); return
        try:
            res = self.service.save(refiner_code=self.refcode.get(), items=self._rows, bill_date=self.tdate.get())
        except (RefineryBillError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._rows = []; self.grid_widget.set_rows([])
        self.status.configure(text=f'Saved {res["doc_no"]} (slno {res["slno"]}, {res["items"]} item(s))', text_color="#1E8449")
