"""Point Card window."""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import PointCardError, PointCardService

_FIELDS = [("pcard", "Point Card"), ("isubgrp", "Sub-Group"), ("pointbasedon", "Point Based On"),
           ("valuefor1point", "Value for 1 Point"), ("valueperpoint", "Value per Point"),
           ("minsalesamt", "Min Sales Amt"), ("rounddown", "Round Down (Y/N)")]


class PointCardView(ctk.CTkFrame):
    TITLE = "Point Card"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PointCardService(database, session)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 6))
        self.grid_widget = DataGrid(self, columns=[("pcard", "Card", 90), ("isubgrp", "Sub-Grp", 90),
                                    ("valueperpoint", "Val/Pt", 90), ("minsalesamt", "Min Sales", 100)],
                                    on_select=self._sel, key_field="pcard")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)
        form = ctk.CTkScrollableFrame(self, width=260, label_text="Point Card"); form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        self._e = {}
        for key, label in _FIELDS:
            ctk.CTkLabel(form, text=label).pack(anchor="w", padx=10, pady=(4, 0))
            e = ctk.CTkEntry(form, width=200); e.pack(anchor="w", padx=10); self._e[key] = e
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.pack(anchor="w", padx=10, pady=8)
        ctk.CTkButton(bt, text="New", width=58, command=self._new).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Save", width=58, command=self._save).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Delete", width=58, fg_color="#B03A2E", hover_color="#943126", command=self._del).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=230); self.status.pack(anchor="w", padx=10)
        self._reload()

    def _reload(self):
        try:
            self.grid_widget.set_rows(self.service.list())
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _sel(self, row):
        full = next((r for r in self.service.list() if r["pcard"] == row.get("pcard") and r["isubgrp"] == row.get("isubgrp")), row)
        for key, e in self._e.items():
            e.delete(0, "end"); e.insert(0, str(full.get(key) if full.get(key) is not None else ""))

    def _new(self):
        for e in self._e.values():
            e.delete(0, "end")
        self.grid_widget.clear_selection()

    def _save(self):
        try:
            self.service.save({k: e.get() for k, e in self._e.items()})
        except (PointCardError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text="Saved.", text_color="#1E8449")

    def _del(self):
        if not self._e["pcard"].get() or not messagebox.askyesno("Delete", "Delete this entry?"):
            return
        self.service.delete(self._e["pcard"].get(), self._e["isubgrp"].get())
        self._new(); self._reload(); self.status.configure(text="Deleted.", text_color="#1E8449")
