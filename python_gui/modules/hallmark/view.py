"""Hallmark records window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import HallmarkService

_F = [("batch_no", "Batch No"), ("item_code", "Item Code"), ("barcode", "Barcode"),
      ("huid", "HUID"), ("bis_centre", "BIS Centre"), ("purity_grade", "Purity Grade"),
      ("purity_name", "Purity Name"), ("weight", "Weight"), ("certificate_no", "Certificate No"),
      ("hallmark_date", "Date"), ("article_desc", "Article")]


class HallmarkView(ctk.CTkFrame):
    TITLE = "Hallmark"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = HallmarkService(database, session)
        self._id = 0
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.grid_widget = DataGrid(self, columns=[("id", "ID", 50), ("batch_no", "Batch", 90),
                                    ("item_code", "Item", 90), ("huid", "HUID", 110), ("weight", "Wt", 70)],
                                    on_select=self._sel, key_field="id")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)
        form = ctk.CTkScrollableFrame(self, width=260, label_text="Record"); form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        self._e = {}
        for k, lbl in _F:
            ctk.CTkLabel(form, text=lbl).pack(anchor="w", padx=10, pady=(4, 0))
            e = ctk.CTkEntry(form, width=200); e.pack(anchor="w", padx=10); self._e[k] = e
        self._e["hallmark_date"].insert(0, date.today().isoformat())
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.pack(anchor="w", padx=10, pady=8)
        ctk.CTkButton(bt, text="New", width=58, command=self._new).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Save", width=58, command=self._save).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=230); self.status.pack(anchor="w", padx=10)
        if not self.service.available():
            self.status.configure(text="hallmark_records table absent on this DB.", text_color=("gray40", "gray70"))
        self._reload()

    def _reload(self):
        try:
            self.grid_widget.set_rows(self.service.list())
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _sel(self, row):
        self._id = int(row.get("id") or 0)
        for k, e in self._e.items():
            e.delete(0, "end"); e.insert(0, str(row.get(k) if row.get(k) is not None else ""))

    def _new(self):
        self._id = 0
        for e in self._e.values():
            e.delete(0, "end")
        self._e["hallmark_date"].insert(0, date.today().isoformat())

    def _save(self):
        data = {k: e.get() for k, e in self._e.items()}; data["id"] = self._id
        try:
            self.service.save(data)
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text="Saved.", text_color="#1E8449")
