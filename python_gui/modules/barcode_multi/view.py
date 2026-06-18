"""Barcode Multi-Entry window — bulk barcode creation."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from .service import BarcodeMultiError, BarcodeMultiService

_FIELDS = [("barcode", "Barcode"), ("itemcode", "Item"), ("qty", "Qty"), ("weight", "Weight"),
           ("stwgt", "Stone Wt"), ("mcrate", "MC Rate"), ("vaperc", "VA%")]


class BarcodeMultiEntryView(ctk.CTkFrame):
    TITLE = "Barcode Multi-Entry"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = BarcodeMultiService(PostingEngine(database), session, control=getattr(session, "gilevel", 1))
        self._rows: list[dict] = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Date").pack(side="left", padx=(16, 4))
        self.tdate = ctk.CTkEntry(head, width=110); self.tdate.pack(side="left"); self.tdate.insert(0, date.today().isoformat())
        try:
            ctk.CTkLabel(head, text=f"Next: {self.service.next_barcode()} · {self.service.next_doc_no()}").pack(side="left", padx=12)
        except Exception:
            pass
        ctk.CTkButton(head, text="Save Batch", width=110, command=self._save).pack(side="right", padx=6)
        entry = ctk.CTkFrame(self, fg_color="transparent"); entry.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        self.inputs: dict[str, ctk.CTkEntry] = {}
        for key, label in _FIELDS:
            ctk.CTkLabel(entry, text=label).pack(side="left", padx=(6, 2))
            e = ctk.CTkEntry(entry, width=90); e.pack(side="left"); self.inputs[key] = e
        ctk.CTkButton(entry, text="Add Row", width=80, command=self._add).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=[(k, lbl, 90) for k, lbl in _FIELDS], key_field="barcode")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=3, column=0, sticky="ew", padx=14, pady=4)

    def _add(self):
        row = {k: (e.get() or "").strip() for k, e in self.inputs.items()}
        if not row.get("barcode") or not row.get("itemcode"):
            self.status.configure(text="Barcode and Item are required.", text_color="#C0392B"); return
        self._rows.append(row)
        self.grid_widget.set_rows(self._rows)
        for e in self.inputs.values():
            e.delete(0, "end")

    def _save(self):
        if not self._rows:
            self.status.configure(text="No rows to save.", text_color="#C0392B"); return
        try:
            res = self.service.save(self._rows, tdate=self.tdate.get())
        except (BarcodeMultiError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._rows = []; self.grid_widget.set_rows([])
        self.status.configure(text=f'Saved {res["saved"]} barcode(s) — {res["docno"]}', text_color="#1E8449")
