"""Counters window (code/name/startbillno master)."""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import CountersRepo
from .service import CountersError, CountersService


class CountersView(ctk.CTkFrame):
    TITLE = "Counters"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = CountersService(CountersRepo(database), session)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 6))
        self.grid_widget = DataGrid(self, columns=[("code", "Code", 90), ("name", "Name", 160),
                                    ("startbillno", "Start Bill No", 110)],
                                    on_select=self._on_select, key_field="code")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)

        form = ctk.CTkFrame(self, width=240); form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        ctk.CTkLabel(form, text="Code").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.code = ctk.CTkEntry(form, width=120); self.code.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="w")
        ctk.CTkLabel(form, text="Name").grid(row=2, column=0, sticky="w", padx=10)
        self.name = ctk.CTkEntry(form, width=180); self.name.grid(row=3, column=0, padx=10, pady=(0, 6), sticky="w")
        ctk.CTkLabel(form, text="Start Bill No").grid(row=4, column=0, sticky="w", padx=10)
        self.start = ctk.CTkEntry(form, width=120); self.start.grid(row=5, column=0, padx=10, pady=(0, 6), sticky="w")
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.grid(row=6, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkButton(bt, text="New", width=58, command=self._new).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Save", width=58, command=self._save).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Delete", width=58, fg_color="#B03A2E", hover_color="#943126", command=self._delete).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=210); self.status.grid(row=7, column=0, padx=10, sticky="w")
        self._reload()

    def _reload(self):
        try:
            self.grid_widget.set_rows(self.service.list())
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        self._set(self.code, row.get("code")); self.code.configure(state="disabled")
        self._set(self.name, row.get("name")); self._set(self.start, row.get("startbillno") or 0)

    @staticmethod
    def _set(e, v):
        e.configure(state="normal"); e.delete(0, "end"); e.insert(0, str(v if v is not None else ""))

    def _new(self):
        self._set(self.code, ""); self._set(self.name, ""); self._set(self.start, "0")
        self.grid_widget.clear_selection()

    def _save(self):
        try:
            self.service.save(self.code.get(), self.name.get(), self.start.get() or 0)
        except CountersError as exc:
            self.status.configure(text=str(exc), text_color="#C0392B"); return
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text="Saved.", text_color="#1E8449")

    def _delete(self):
        code = (self.code.get() or "").strip().upper()
        if not code or not messagebox.askyesno("Delete", f"Delete '{code}'?"):
            return
        try:
            self.service.delete(code)
        except CountersError as exc:
            messagebox.showwarning("Cannot delete", str(exc)); return
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._new(); self._reload(); self.status.configure(text="Deleted.", text_color="#1E8449")
