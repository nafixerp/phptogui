"""Repair Complaints master window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import RepairComplaintsService


class RepairComplaintsView(ctk.CTkFrame):
    TITLE = "Repair Complaints"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = RepairComplaintsService(database, session)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.entry = ctk.CTkEntry(head, width=200, placeholder_text="new complaint"); self.entry.pack(side="left", padx=(16, 4))
        ctk.CTkButton(head, text="Add", width=60, command=self._add).pack(side="left", padx=4)
        ctk.CTkButton(head, text="Delete Selected", width=120, command=self._delete).pack(side="right", padx=6)
        self.grid_widget = DataGrid(self, columns=[("part", "Complaint", 360)], on_select=self._on_select, key_field="part")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=4)
        self._sel = None
        self._reload()

    def _reload(self):
        try:
            self.grid_widget.set_rows([{"part": p} for p in self.service.list()])
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        self._sel = row.get("part")

    def _add(self):
        val = (self.entry.get() or "").strip()
        if not val:
            return
        try:
            current = self.service.list()
            self.service.save(current + [val])
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.entry.delete(0, "end"); self._reload(); self.status.configure(text="Saved.", text_color="#1E8449")

    def _delete(self):
        if not self._sel:
            self.status.configure(text="Select a complaint.", text_color="#C0392B"); return
        try:
            remaining = [p for p in self.service.list() if p != self._sel]
            self.service.save(remaining, deleted=[self._sel])
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text="Deleted.", text_color="#1E8449")
