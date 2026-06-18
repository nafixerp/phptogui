"""Gift Table window."""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import GiftError, GiftTableService


class GiftTableView(ctk.CTkFrame):
    TITLE = "Gift Table"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = GiftTableService(database, session)
        self._orig = None
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 6))
        self.grid_widget = DataGrid(self, columns=[("points", "Points", 100), ("particulars", "Gift", 260)],
                                    on_select=self._sel, key_field="points")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)
        form = ctk.CTkFrame(self, width=240); form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        ctk.CTkLabel(form, text="Points").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.points = ctk.CTkEntry(form, width=120); self.points.grid(row=1, column=0, padx=10, sticky="w")
        ctk.CTkLabel(form, text="Gift / Particulars").grid(row=2, column=0, sticky="w", padx=10)
        self.part = ctk.CTkEntry(form, width=200); self.part.grid(row=3, column=0, padx=10, pady=(0, 6), sticky="w")
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.grid(row=4, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkButton(bt, text="New", width=58, command=self._new).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Save", width=58, command=self._save).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Delete", width=58, fg_color="#B03A2E", hover_color="#943126", command=self._del).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=210); self.status.grid(row=5, column=0, padx=10, sticky="w")
        self._reload()

    def _reload(self):
        try:
            self.grid_widget.set_rows(self.service.list())
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _sel(self, row):
        self._orig = row.get("points")
        for e, v in ((self.points, row.get("points")), (self.part, row.get("particulars"))):
            e.delete(0, "end"); e.insert(0, str(v if v is not None else ""))

    def _new(self):
        self._orig = None
        for e in (self.points, self.part):
            e.delete(0, "end")
        self.grid_widget.clear_selection()

    def _save(self):
        try:
            self.service.save(self.points.get(), self.part.get(), self._orig)
        except (GiftError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text="Saved.", text_color="#1E8449")

    def _del(self):
        if not self.points.get() or not messagebox.askyesno("Delete", "Delete this row?"):
            return
        self.service.delete(self.points.get()); self._new(); self._reload()
        self.status.configure(text="Deleted.", text_color="#1E8449")
