"""Ruff Work memo window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import RuffWorkService

_FIELDS = [("party", "Party"), ("item", "Item"), ("qty", "Qty"), ("weight", "Weight"),
           ("amount", "Amount"), ("person", "Person")]


class RuffWorkView(ctk.CTkFrame):
    TITLE = "Ruff Work"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = RuffWorkService(database, control=getattr(session, "gilevel", 1))
        self._sel = None
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="Reload", width=70, command=self._reload).pack(side="left", padx=8)
        ctk.CTkButton(head, text="Delete Selected", width=120, command=self._delete).pack(side="right", padx=6)
        entry = ctk.CTkFrame(self, fg_color="transparent"); entry.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        self.inputs: dict[str, ctk.CTkEntry] = {}
        for key, label in _FIELDS:
            ctk.CTkLabel(entry, text=label).pack(side="left", padx=(6, 2))
            e = ctk.CTkEntry(entry, width=90); e.pack(side="left"); self.inputs[key] = e
        ctk.CTkButton(entry, text="Save Row", width=80, command=self._save).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=[("slno", "Slno", 70)] + [(k, lbl, 100) for k, lbl in _FIELDS],
                                    on_select=self._on_select, key_field="slno")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=3, column=0, sticky="ew", padx=14, pady=4)
        self._reload()

    def _reload(self):
        try:
            rows = self.service.list()
            self.grid_widget.set_rows([{"slno": r.get("slno"), **{k: str(r.get(k) or "") for k, _ in _FIELDS}} for r in rows])
            self.status.configure(text=f"{len(rows)} row(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        self._sel = row.get("slno")
        for k, e in self.inputs.items():
            e.delete(0, "end"); e.insert(0, str(row.get(k) or ""))

    def _save(self):
        row = {k: e.get() for k, e in self.inputs.items()}
        row["tdate"] = date.today().isoformat()
        if self._sel:
            row["slno"] = self._sel
        try:
            self.service.save([row])
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._sel = None; self._reload(); self.status.configure(text="Saved.", text_color="#1E8449")

    def _delete(self):
        if not self._sel:
            self.status.configure(text="Select a row.", text_color="#C0392B"); return
        try:
            self.service.delete(self._sel)
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._sel = None; self._reload(); self.status.configure(text="Deleted.", text_color="#1E8449")
