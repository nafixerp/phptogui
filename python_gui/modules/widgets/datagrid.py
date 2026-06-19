"""Reusable read grid for master/list screens.

Wraps ttk.Treeview (ships with Tkinter, renders a real multi-column grid and
coexists with customtkinter). Feed it column specs and a list of row dicts.
"""

from __future__ import annotations

from tkinter import ttk
from typing import Callable

import customtkinter as ctk


class DataGrid(ctk.CTkFrame):
    def __init__(
        self,
        master,
        columns: list[tuple[str, str, int]],   # (key, heading, width)
        on_select: Callable[[dict], None] | None = None,
        key_field: str | None = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.columns = columns
        self.key_field = key_field or (columns[0][0] if columns else "")
        self.on_select = on_select
        self._rows: dict[str, dict] = {}

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        keys = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=keys, show="headings", selectmode="browse")
        for key, heading, width in columns:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<<TreeviewSelect>>", self._handle_select)

    def set_rows(self, rows: list[dict]) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        for row in rows:
            ident = str(row.get(self.key_field, ""))
            values = [self._fmt(row.get(c[0])) for c in self.columns]
            self.tree.insert("", "end", iid=ident, values=values)
            self._rows[ident] = row

    def selected(self) -> dict | None:
        sel = self.tree.selection()
        return self._rows.get(sel[0]) if sel else None

    def select_key(self, key: str) -> None:
        key = str(key)
        if key in self._rows:
            self.tree.selection_set(key)
            self.tree.see(key)

    def clear_selection(self) -> None:
        if self.tree.selection():
            self.tree.selection_remove(self.tree.selection())

    @staticmethod
    def _fmt(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Yes" if value else "No"
        return str(value)

    def _handle_select(self, _event) -> None:
        if self.on_select:
            row = self.selected()
            if row is not None:
                self.on_select(row)
