"""States Master window — grid of state codes/names with upsert save."""
from __future__ import annotations

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import StatesError, StatesMasterService


class StatesMasterView(ctk.CTkFrame):
    TITLE = "States"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = StatesMasterService(database, session)
        self._rows: list[dict] = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 6))
        self.grid_widget = DataGrid(self, columns=[("code", "Code", 90), ("name", "State", 240)],
                                    on_select=self._sel, key_field="code")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)
        form = ctk.CTkFrame(self, width=240); form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        ctk.CTkLabel(form, text="Code").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.code = ctk.CTkEntry(form, width=120); self.code.grid(row=1, column=0, padx=10, sticky="w")
        ctk.CTkLabel(form, text="State name").grid(row=2, column=0, sticky="w", padx=10)
        self.name = ctk.CTkEntry(form, width=220); self.name.grid(row=3, column=0, padx=10, sticky="w")
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.grid(row=4, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkButton(bt, text="New", width=54, command=self._new).pack(side="left", padx=(0, 4))
        ctk.CTkButton(bt, text="Apply", width=58, command=self._apply).pack(side="left", padx=(0, 4))
        ctk.CTkButton(bt, text="Delete", width=64, fg_color="#B03A2E", hover_color="#943126",
                      command=self._del).pack(side="left")
        ctk.CTkButton(form, text="Save All", width=120, command=self._save).grid(row=5, column=0, padx=10, pady=(2, 4), sticky="w")
        self.status = ctk.CTkLabel(form, text="", wraplength=215); self.status.grid(row=6, column=0, padx=10, sticky="w")
        self._reload()

    def _reload(self):
        self._rows = list(self.service.list())
        self.grid_widget.set_rows(self._rows)

    def _sel(self, row):
        if not row:
            return
        self._new()
        self.code.insert(0, row.get("code", "")); self.name.insert(0, row.get("name", ""))

    def _new(self):
        self.code.delete(0, "end"); self.name.delete(0, "end"); self.status.configure(text="")

    def _apply(self):
        code = (self.code.get() or "").strip().upper()
        name = (self.name.get() or "").strip()
        if not code or not name:
            self.status.configure(text="Code and name are required", text_color="#C0392B"); return
        self._rows = [r for r in self._rows if str(r.get("code", "")).strip().upper() != code]
        self._rows.append({"code": code, "name": name})
        self._rows.sort(key=lambda r: str(r.get("code", "")))
        self.grid_widget.set_rows(self._rows)
        self.status.configure(text=f"{code} staged. Press Save All to persist.", text_color="#1E8449")

    def _del(self):
        sel = self.grid_widget.selected()
        if not sel:
            return
        try:
            msg = self.service.delete(sel.get("code", ""))
        except (StatesError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload()
        self.status.configure(text=msg, text_color="#1E8449")

    def _save(self):
        try:
            res = self.service.save_all(self._rows)
        except (StatesError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload()
        self.status.configure(text=res["message"], text_color="#1E8449")
