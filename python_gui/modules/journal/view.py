"""Journal voucher window — balanced multi-line entry."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from .service import JournalError, JournalService


class JournalView(ctk.CTkFrame):
    TITLE = "Journal"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = JournalService(PostingEngine(database), session)
        self._rows: list[dict] = []
        self._slno = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Date").pack(side="left", padx=(16, 4))
        self.tdate = ctk.CTkEntry(head, width=120); self.tdate.pack(side="left")
        self.tdate.insert(0, date.today().isoformat())
        ctk.CTkLabel(head, text="Narration").pack(side="left", padx=(12, 4))
        self.narration = ctk.CTkEntry(head, width=240); self.narration.pack(side="left")

        self.grid_widget = DataGrid(self, columns=[("particulars", "Account", 120),
                                    ("amountd", "Debit", 100), ("amountc", "Credit", 100),
                                    ("rownote", "Note", 160)], on_select=self._on_select, key_field="particulars")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)

        form = ctk.CTkFrame(self, width=240); form.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)
        self._inp = {}
        for key, label in [("particulars", "Account Code"), ("amountd", "Debit"),
                           ("amountc", "Credit"), ("rownote", "Note")]:
            ctk.CTkLabel(form, text=label).pack(anchor="w", padx=10, pady=(4, 0))
            e = ctk.CTkEntry(form, width=200); e.pack(anchor="w", padx=10); self._inp[key] = e
        ctk.CTkButton(form, text="Add Row", width=100, command=self._add).pack(anchor="w", padx=10, pady=6)
        ctk.CTkButton(form, text="Remove Selected", width=140, command=self._remove).pack(anchor="w", padx=10)
        self.totals = ctk.CTkLabel(form, text="Dr 0.00 / Cr 0.00"); self.totals.pack(anchor="w", padx=10, pady=6)
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.pack(anchor="w", padx=10, pady=4)
        ctk.CTkButton(bt, text="New", width=60, command=self._new).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bt, text="Save", width=60, command=self._save).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=210); self.status.pack(anchor="w", padx=10)

    def _on_select(self, row):
        for k, e in self._inp.items():
            e.delete(0, "end"); e.insert(0, str(row.get(k) or ""))

    def _add(self):
        self._rows.append({k: self._inp[k].get() for k in self._inp})
        self.grid_widget.set_rows(self._rows)
        self._recalc()

    def _remove(self):
        sel = self.grid_widget.selected()
        if sel in self._rows:
            self._rows.remove(sel); self.grid_widget.set_rows(self._rows); self._recalc()

    def _recalc(self):
        dr = sum((money(r.get("amountd", 0)) for r in self._rows), Decimal("0"))
        cr = sum((money(r.get("amountc", 0)) for r in self._rows), Decimal("0"))
        self.totals.configure(text=f"Dr {dr} / Cr {cr}",
                              text_color="#1E8449" if dr == cr and dr > 0 else ("gray30", "gray70"))

    def _new(self):
        self._rows = []; self._slno = 0; self.grid_widget.set_rows([])
        self.narration.delete(0, "end"); self._recalc()
        self.status.configure(text="New journal", text_color=("gray30", "gray70"))

    def _save(self):
        try:
            res = self.service.save(self._rows, self.tdate.get(), self.narration.get(), "A")
        except (JournalError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._slno = res["slno"]
        self.status.configure(text=f"Saved {res['vchno']} (slno {res['slno']})", text_color="#1E8449")
