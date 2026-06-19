"""Salesman Master window — grid of salesmen with full-replace save."""
from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import SalesmanError, SalesmanMasterService


class SalesmanMasterView(ctk.CTkFrame):
    TITLE = "Salesman Master"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = SalesmanMasterService(database, session)
        self._rows: list[dict] = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 6))
        self.grid_widget = DataGrid(self, columns=[("code", "Code", 90), ("name", "Name", 200),
                                                   ("accode", "Account", 110), ("active", "Active", 70)],
                                    on_select=self._sel, key_field="code")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)
        form = ctk.CTkFrame(self, width=260); form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        ctk.CTkLabel(form, text="Code").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.code = ctk.CTkEntry(form, width=140); self.code.grid(row=1, column=0, padx=10, sticky="w")
        ctk.CTkLabel(form, text="Name").grid(row=2, column=0, sticky="w", padx=10)
        self.name = ctk.CTkEntry(form, width=220); self.name.grid(row=3, column=0, padx=10, sticky="w")
        ctk.CTkLabel(form, text="Account code").grid(row=4, column=0, sticky="w", padx=10)
        self.accode = ctk.CTkEntry(form, width=140); self.accode.grid(row=5, column=0, padx=10, sticky="w")
        self.active = ctk.CTkCheckBox(form, text="Active"); self.active.grid(row=6, column=0, padx=10, pady=6, sticky="w")
        self.active.select()
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.grid(row=7, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkButton(bt, text="New", width=54, command=self._new).pack(side="left", padx=(0, 4))
        ctk.CTkButton(bt, text="Apply", width=58, command=self._apply).pack(side="left", padx=(0, 4))
        ctk.CTkButton(bt, text="Remove", width=64, fg_color="#B03A2E", hover_color="#943126",
                      command=self._remove).pack(side="left")
        ctk.CTkButton(form, text="Save All", width=120, command=self._save).grid(row=8, column=0, padx=10, pady=(2, 4), sticky="w")
        self.status = ctk.CTkLabel(form, text="", wraplength=230); self.status.grid(row=9, column=0, padx=10, sticky="w")
        self._reload()

    def _reload(self):
        self._rows = list(self.service.list())
        self.grid_widget.set_rows(self._rows)

    def _sel(self, row):
        if not row:
            return
        self._new()
        self.code.insert(0, row.get("code", "")); self.name.insert(0, row.get("name", ""))
        self.accode.insert(0, row.get("accode", ""))
        (self.active.select if str(row.get("active", "Y")).upper() != "N" else self.active.deselect)()

    def _new(self):
        for e in (self.code, self.name, self.accode):
            e.delete(0, "end")
        self.active.select(); self.status.configure(text="")

    def _apply(self):
        code = (self.code.get() or "").strip().upper()
        if not code:
            self.status.configure(text="Code is required", text_color="#C0392B"); return
        row = {"code": code, "name": (self.name.get() or "").strip().upper(),
               "accode": (self.accode.get() or "").strip().upper(),
               "active": "Y" if self.active.get() else "N"}
        self._rows = [r for r in self._rows if str(r.get("code", "")).strip().upper() != code]
        self._rows.append(row)
        self._rows.sort(key=lambda r: str(r.get("code", "")))
        self.grid_widget.set_rows(self._rows)
        self.status.configure(text=f"{code} staged. Press Save All to persist.", text_color="#1E8449")

    def _remove(self):
        sel = self.grid_widget.selected()
        if not sel:
            return
        code = str(sel.get("code", "")).strip().upper()
        try:
            n = self.service.usage_count(code)
        except Exception:
            n = 0
        if n > 0 and not messagebox.askyesno("In use", f"{code} is used in {n} order(s). Remove anyway?"):
            return
        self._rows = [r for r in self._rows if str(r.get("code", "")).strip().upper() != code]
        self.grid_widget.set_rows(self._rows)
        self.status.configure(text=f"{code} removed from list (Save All to persist).")

    def _save(self):
        try:
            msg = self.service.save_all(self._rows)
        except (SalesmanError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload()
        self.status.configure(text=msg, text_color="#1E8449")
