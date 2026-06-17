"""MC Table window — weight-slab making charges per item code + purity type."""

from __future__ import annotations

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import MCTableRepo
from .service import MCTableError, MCTableService

_COLS = [("weight1", "Wt From", 80), ("weight2", "Wt To", 80), ("mc", "MC", 80),
         ("mcpergm", "MC/gm", 80), ("mcperqty", "MC/qty", 80), ("vaperc", "VA %", 70)]


class MCTableView(ctk.CTkFrame):
    TITLE = "MC Table"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = MCTableService(MCTableRepo(database), session)
        self._entries: list[dict] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Item Code").pack(side="left", padx=(16, 4))
        self.code = ctk.CTkEntry(head, width=120); self.code.pack(side="left")
        ctk.CTkLabel(head, text="Purity (iqtype)").pack(side="left", padx=(12, 4))
        self.iqtype = ctk.CTkEntry(head, width=90); self.iqtype.pack(side="left")
        ctk.CTkButton(head, text="Load", width=70, command=self._load).pack(side="left", padx=8)

        self.grid_widget = DataGrid(self, columns=_COLS, on_select=self._on_select, key_field="weight1")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)

        form = ctk.CTkFrame(self, width=240); form.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)
        self._inputs: dict[str, ctk.CTkEntry] = {}
        for key, label, _w in _COLS:
            ctk.CTkLabel(form, text=label).pack(anchor="w", padx=10, pady=(4, 0))
            e = ctk.CTkEntry(form, width=140); e.pack(anchor="w", padx=10); e.insert(0, "0")
            self._inputs[key] = e
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.pack(anchor="w", padx=10, pady=8)
        ctk.CTkButton(bt, text="Add Slab", width=80, command=self._add).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bt, text="Remove Sel", width=90, command=self._remove).pack(side="left")
        ctk.CTkButton(form, text="Save All Slabs", width=180, command=self._save).pack(anchor="w", padx=10, pady=(4, 6))
        self.status = ctk.CTkLabel(form, text="", wraplength=210); self.status.pack(anchor="w", padx=10)

    def _load(self):
        code = self.code.get().strip()
        if not code:
            self.status.configure(text="Enter an item code.", text_color="#C0392B"); return
        try:
            self._entries = [dict(r) for r in self.service.get_for_item(code, self.iqtype.get())]
            self.grid_widget.set_rows(self._entries)
            self.status.configure(text=f"{len(self._entries)} slab(s) loaded.", text_color=("gray30", "gray70"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        for key, e in self._inputs.items():
            e.delete(0, "end"); e.insert(0, str(row.get(key) if row.get(key) is not None else "0"))

    def _add(self):
        self._entries.append({k: self._inputs[k].get() or "0" for k, _l, _w in _COLS})
        self.grid_widget.set_rows(self._entries)

    def _remove(self):
        sel = self.grid_widget.selected()
        if sel in self._entries:
            self._entries.remove(sel)
            self.grid_widget.set_rows(self._entries)

    def _save(self):
        try:
            msg = self.service.save(self.code.get(), self.iqtype.get(), self._entries)
        except MCTableError as exc:
            self.status.configure(text=str(exc), text_color="#C0392B"); return
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._load(); self.status.configure(text=msg, text_color="#1E8449")
