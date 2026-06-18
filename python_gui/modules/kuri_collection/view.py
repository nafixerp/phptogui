"""Kuri / Scheme Collection window."""

from __future__ import annotations

from datetime import date

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from .service import KuriError, KuriCollectionService


class KuriCollectionView(ctk.CTkFrame):
    TITLE = "Scheme / Kuri Collection"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = KuriCollectionService(PostingEngine(database), session)
        self._rows: list[dict] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Date").pack(side="left", padx=(16, 4))
        self.tdate = ctk.CTkEntry(head, width=110); self.tdate.pack(side="left"); self.tdate.insert(0, date.today().isoformat())
        ctk.CTkLabel(head, text="Cash A/c").pack(side="left", padx=(12, 4))
        self.cash = ctk.CTkEntry(head, width=90); self.cash.pack(side="left"); self.cash.insert(0, "CASH")
        ctk.CTkLabel(head, text="Gold Rate").pack(side="left", padx=(12, 4))
        self.rate = ctk.CTkEntry(head, width=80); self.rate.pack(side="left"); self.rate.insert(0, "0")

        self.grid_widget = DataGrid(self, columns=[("code", "Scheme A/c", 120), ("amount", "Amount", 120),
                                    ("agent", "Agent", 100), ("rcptno", "Receipt", 100)], key_field="code")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)

        form = ctk.CTkFrame(self, width=220); form.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)
        self._inp = {}
        for key, label in [("code", "Scheme A/c"), ("amount", "Amount"), ("agent", "Agent"), ("rcptno", "Receipt No")]:
            ctk.CTkLabel(form, text=label).pack(anchor="w", padx=10, pady=(4, 0))
            e = ctk.CTkEntry(form, width=180); e.pack(anchor="w", padx=10); self._inp[key] = e
        ctk.CTkButton(form, text="Add Row", width=100, command=self._add).pack(anchor="w", padx=10, pady=6)
        ctk.CTkButton(form, text="Save Collection", width=160, command=self._save).pack(anchor="w", padx=10)
        self.status = ctk.CTkLabel(form, text="", wraplength=190); self.status.pack(anchor="w", padx=10, pady=6)

    def _add(self):
        self._rows.append({k: self._inp[k].get() for k in self._inp})
        self.grid_widget.set_rows(self._rows)

    def _save(self):
        try:
            res = self.service.collect(self._rows, self.tdate.get(), self.cash.get(), self.rate.get())
        except (KuriError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._rows = []; self.grid_widget.set_rows([])
        self.status.configure(text=f"Saved {res['saved']} collection(s).", text_color="#1E8449")
