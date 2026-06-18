"""Party MC Table window (per-party MC overrides)."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import PartyMCError, PartyMCTableService

_C = [("icode", "Item", 90), ("model", "Model", 90), ("wastage", "Wastage", 80),
      ("mc", "MC", 70), ("mcperc", "MC%", 70), ("touch", "Touch", 70)]


class PartyMCTableView(ctk.CTkFrame):
    TITLE = "Party MC Table"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PartyMCTableService(database, session)
        self._rows = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Party Code").pack(side="left", padx=(16, 4))
        self.pcode = ctk.CTkEntry(head, width=120); self.pcode.pack(side="left")
        ctk.CTkButton(head, text="Load", width=70, command=self._load).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=_C, key_field="icode"); self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)
        form = ctk.CTkFrame(self, width=220); form.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)
        self._inp = {}
        for k, lbl, _w in _C:
            ctk.CTkLabel(form, text=lbl).pack(anchor="w", padx=10, pady=(4, 0))
            e = ctk.CTkEntry(form, width=160); e.pack(anchor="w", padx=10); self._inp[k] = e
        ctk.CTkButton(form, text="Add Row", width=100, command=self._add).pack(anchor="w", padx=10, pady=6)
        ctk.CTkButton(form, text="Save All", width=160, command=self._save).pack(anchor="w", padx=10)
        self.status = ctk.CTkLabel(form, text="", wraplength=190); self.status.pack(anchor="w", padx=10, pady=6)

    def _load(self):
        try:
            self._rows = [dict(r) for r in self.service.get_for_party(self.pcode.get())]
            self.grid_widget.set_rows(self._rows)
            self.status.configure(text=f"{len(self._rows)} row(s).", text_color=("gray30", "gray70"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _add(self):
        self._rows.append({k: self._inp[k].get() for k, _l, _w in _C}); self.grid_widget.set_rows(self._rows)

    def _save(self):
        try:
            msg = self.service.save(self.pcode.get(), self._rows)
        except (PartyMCError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._load(); self.status.configure(text=msg, text_color="#1E8449")
