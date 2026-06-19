"""Other Items master window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import OtherItemsError, OtherItemsService

_FIELDS = [("code", "Code"), ("name", "Name"), ("grp", "Group"), ("srate", "Sale Rate"),
           ("prate", "Purch Rate"), ("cost", "Cost"), ("stock", "Stock")]


class OtherItemsView(ctk.CTkFrame):
    TITLE = "Other Items"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = OtherItemsService(database)
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
            e = ctk.CTkEntry(entry, width=80); e.pack(side="left"); self.inputs[key] = e
        ctk.CTkButton(entry, text="Add", width=60, command=lambda: self._save("add")).pack(side="left", padx=4)
        ctk.CTkButton(entry, text="Update", width=70, command=lambda: self._save("edit")).pack(side="left", padx=4)
        self.grid_widget = DataGrid(self, columns=[(k, lbl, 100) for k, lbl in _FIELDS], on_select=self._on_select, key_field="code")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=3, column=0, sticky="ew", padx=14, pady=4)
        self._reload()

    def _reload(self):
        try:
            rows = self.service.list()
            self.grid_widget.set_rows([{k: str(r.get(k) or "") for k, _ in _FIELDS} for r in rows])
            self.status.configure(text=f"{len(rows)} item(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        self._sel = row.get("code")
        for k, e in self.inputs.items():
            e.delete(0, "end"); e.insert(0, str(row.get(k) or ""))

    def _save(self, mode):
        data = {k: e.get() for k, e in self.inputs.items()}
        try:
            msg = self.service.add(data) if mode == "add" else self.service.edit(data)
        except (OtherItemsError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text=msg, text_color="#1E8449")

    def _delete(self):
        if not self._sel:
            self.status.configure(text="Select an item.", text_color="#C0392B"); return
        try:
            self.service.delete(self._sel)
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text="Deleted.", text_color="#1E8449")
