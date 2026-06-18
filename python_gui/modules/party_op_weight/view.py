"""Party Opening Weight window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import PartyOpWeightError, PartyOpWeightService


class PartyOpWeightView(ctk.CTkFrame):
    TITLE = "Party Opening Weight"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PartyOpWeightService(database, session)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.search = ctk.StringVar()
        e = ctk.CTkEntry(head, width=200, placeholder_text="Search…", textvariable=self.search); e.pack(side="right")
        e.bind("<Return>", lambda _ev: self._reload())
        ctk.CTkButton(head, text="Search", width=70, command=self._reload).pack(side="right", padx=6)
        self.grid_widget = DataGrid(self, columns=[("accode", "Code", 110), ("name", "Name", 200), ("opwgt", "Op Wgt", 110)],
                                    on_select=self._sel, key_field="accode")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)
        form = ctk.CTkFrame(self, width=220); form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        ctk.CTkLabel(form, text="Account").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.code = ctk.CTkEntry(form, width=140); self.code.grid(row=1, column=0, padx=10, sticky="w")
        ctk.CTkLabel(form, text="Opening Weight").grid(row=2, column=0, sticky="w", padx=10)
        self.opwgt = ctk.CTkEntry(form, width=140); self.opwgt.grid(row=3, column=0, padx=10, pady=(0, 6), sticky="w")
        ctk.CTkButton(form, text="Save", width=120, command=self._save).grid(row=4, column=0, padx=10, pady=8, sticky="w")
        self.status = ctk.CTkLabel(form, text="", wraplength=190); self.status.grid(row=5, column=0, padx=10, sticky="w")
        self._reload()

    def _reload(self):
        try:
            self.grid_widget.set_rows(self.service.list_accounts(self.search.get()))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _sel(self, row):
        self.code.delete(0, "end"); self.code.insert(0, str(row.get("accode") or ""))
        self.opwgt.delete(0, "end"); self.opwgt.insert(0, str(row.get("opwgt") or 0))

    def _save(self):
        try:
            msg = self.service.save(self.code.get(), self.opwgt.get() or 0)
        except (PartyOpWeightError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text=msg, text_color="#1E8449")
