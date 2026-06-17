"""Purity Type window (code + touch master, with rename cascade)."""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import PurityTypeRepo
from .service import PurityTypeError, PurityTypeService


class PurityTypeView(ctk.CTkFrame):
    TITLE = "Purity Type"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PurityTypeService(PurityTypeRepo(database), session)
        self._original: str | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 6))
        self.grid_widget = DataGrid(self, columns=[("code", "Code", 120), ("touch", "Touch", 120)],
                                    on_select=self._on_select, key_field="code")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)

        form = ctk.CTkFrame(self, width=240); form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        ctk.CTkLabel(form, text="Code").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.code = ctk.CTkEntry(form, width=140); self.code.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="w")
        ctk.CTkLabel(form, text="Touch").grid(row=2, column=0, sticky="w", padx=10)
        self.touch = ctk.CTkEntry(form, width=140); self.touch.grid(row=3, column=0, padx=10, pady=(0, 6), sticky="w")
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.grid(row=4, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkButton(bt, text="New", width=58, command=self._new).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Save", width=58, command=self._save).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Delete", width=58, fg_color="#B03A2E", hover_color="#943126", command=self._delete).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=210); self.status.grid(row=5, column=0, padx=10, sticky="w")
        self._reload()

    def _reload(self):
        try:
            self.grid_widget.set_rows(self.service.list())
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        self._original = str(row.get("code", "")).strip()
        self._set(self.code, row.get("code")); self._set(self.touch, row.get("touch"))

    @staticmethod
    def _set(e, v):
        e.delete(0, "end"); e.insert(0, str(v if v is not None else ""))

    def _new(self):
        self._original = None; self._set(self.code, ""); self._set(self.touch, "0")
        self.grid_widget.clear_selection()

    def _save(self):
        try:
            self.service.save_row(self.code.get(), self.touch.get(), self._original or "")
        except PurityTypeError as exc:
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
        except PurityTypeError as exc:
            messagebox.showwarning("Cannot delete", str(exc)); return
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._new(); self._reload(); self.status.configure(text="Deleted.", text_color="#1E8449")
