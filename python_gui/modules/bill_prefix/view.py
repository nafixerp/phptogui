"""Bill Prefix / Invoice Settings window (per-row edit of salestype)."""

from __future__ import annotations

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import BillPrefixRepo
from .service import BillPrefixError, BillPrefixService

_FIELDS = [
    ("code", "Code"), ("name", "Name"), ("taxperc", "Tax %"), ("formno", "Form No"),
    ("prefix", "Sales Prefix"), ("startno", "Sales Start No"),
    ("srprefix", "S.Return Prefix"), ("srstartno", "S.Return Start No"),
    ("pprefix", "Purchase Prefix"), ("pstartno", "Purchase Start No"),
    ("prprefix", "P.Return Prefix"), ("prstartno", "P.Return Start No"),
]


class BillPrefixView(ctk.CTkFrame):
    TITLE = "Bill Prefix / Invoice Settings"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = BillPrefixService(BillPrefixRepo(database), session)
        self._entries: dict[str, ctk.CTkEntry] = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 6))
        self.grid_widget = DataGrid(self, columns=[("code", "Code", 80), ("name", "Name", 160),
                                    ("prefix", "Sales", 70), ("startno", "Start", 70)],
                                    on_select=self._on_select, key_field="code")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)

        form = ctk.CTkScrollableFrame(self, width=300, label_text="Type")
        form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        for key, label in _FIELDS:
            ctk.CTkLabel(form, text=label).pack(anchor="w", padx=10, pady=(4, 0))
            e = ctk.CTkEntry(form, width=240); e.pack(anchor="w", padx=10, pady=(0, 2))
            self._entries[key] = e
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.pack(anchor="w", padx=10, pady=10)
        ctk.CTkButton(bt, text="New", width=64, command=self._new).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bt, text="Save", width=64, command=self._save).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=270); self.status.pack(anchor="w", padx=10)
        self._reload()

    def _reload(self):
        try:
            self._rows = self.service.retrieve()
            self.grid_widget.set_rows(self._rows)
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        full = next((r for r in self._rows if r["code"] == row.get("code")), row)
        for key, e in self._entries.items():
            e.delete(0, "end"); e.insert(0, str(full.get(key) if full.get(key) is not None else ""))
        self._entries["code"].configure(state="disabled")

    def _new(self):
        for key, e in self._entries.items():
            e.configure(state="normal"); e.delete(0, "end")
        self.grid_widget.clear_selection()

    def _save(self):
        data = {k: e.get() for k, e in self._entries.items()}
        try:
            msg = self.service.save_row(data)
        except BillPrefixError as exc:
            self.status.configure(text=str(exc), text_color="#C0392B"); return
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text=msg, text_color="#1E8449")
