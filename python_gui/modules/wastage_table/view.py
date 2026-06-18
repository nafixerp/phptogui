"""Wastage Table window — weight-slab wastage per item code + purity."""

from __future__ import annotations

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import WastageError, WastageTableService

_COLS = [("weight1", "Wt From", 90), ("weight2", "Wt To", 90), ("wastage", "Wastage", 90), ("perc", "Perc", 80)]


class WastageTableView(ctk.CTkFrame):
    TITLE = "Wastage Table"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = WastageTableService(database, session)
        self._entries: list[dict] = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Item Code").pack(side="left", padx=(16, 4))
        self.code = ctk.CTkEntry(head, width=120); self.code.pack(side="left")
        ctk.CTkLabel(head, text="Purity").pack(side="left", padx=(12, 4))
        self.iqtype = ctk.CTkEntry(head, width=80); self.iqtype.pack(side="left")
        ctk.CTkButton(head, text="Load", width=70, command=self._load).pack(side="left", padx=8)

        self.grid_widget = DataGrid(self, columns=_COLS, key_field="weight1")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)
        form = ctk.CTkFrame(self, width=220); form.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)
        self._inp = {}
        for key, label, _w in _COLS:
            ctk.CTkLabel(form, text=label).pack(anchor="w", padx=10, pady=(4, 0))
            e = ctk.CTkEntry(form, width=140); e.pack(anchor="w", padx=10); e.insert(0, "0"); self._inp[key] = e
        ctk.CTkButton(form, text="Add Slab", width=100, command=self._add).pack(anchor="w", padx=10, pady=8)
        ctk.CTkButton(form, text="Save All", width=160, command=self._save).pack(anchor="w", padx=10)
        self.status = ctk.CTkLabel(form, text="", wraplength=190); self.status.pack(anchor="w", padx=10, pady=6)

    def _load(self):
        try:
            self._entries = [dict(r) for r in self.service.get_for_item(self.code.get(), self.iqtype.get())]
            self.grid_widget.set_rows(self._entries)
            self.status.configure(text=f"{len(self._entries)} slab(s).", text_color=("gray30", "gray70"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _add(self):
        self._entries.append({k: self._inp[k].get() for k, _l, _w in _COLS})
        self.grid_widget.set_rows(self._entries)

    def _save(self):
        try:
            msg = self.service.save(self.code.get(), self.iqtype.get(), self._entries)
        except (WastageError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._load(); self.status.configure(text=msg, text_color="#1E8449")
