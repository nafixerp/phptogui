"""Misc Reports window — Non-Transactional Days / Gold Rate History."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import MiscReportsService

_MODES = ["Non-Transactional Days", "Gold Rate History"]


class MiscReportsView(ctk.CTkFrame):
    TITLE = "Misc Reports"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = MiscReportsService(database)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.mode = ctk.CTkOptionMenu(head, width=200, values=_MODES, command=lambda _v: self._show()); self.mode.pack(side="left", padx=10)
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(8, 4))
        self.d1 = ctk.CTkEntry(head, width=110); self.d1.pack(side="left"); self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(8, 4))
        self.d2 = ctk.CTkEntry(head, width=110); self.d2.pack(side="left"); self.d2.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("a", "", 100)], key_field="a"); self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._show()

    def _set_cols(self, cols):
        self.grid_widget.destroy()
        self.grid_widget = DataGrid(self, columns=cols, key_field=cols[0][0]); self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _show(self):
        try:
            if self.mode.get() == "Non-Transactional Days":
                rows = self.service.non_transactional_days(self.d1.get(), self.d2.get())
                self._set_cols([("sno", "S.No", 80), ("tdate", "Holiday (no transactions)", 260)])
                self.grid_widget.set_rows([{"sno": r["sno"], "tdate": r["tdate"]} for r in rows])
                self.summary.configure(text=f"{len(rows)} non-transactional day(s).", text_color=("gray20", "gray80"))
            else:
                rows = self.service.gold_rate_history(self.d1.get(), self.d2.get())
                self._set_cols([("tdate", "Date", 120), ("grate", "Gold 22K", 120), ("g18rate", "Gold 18K", 120),
                                ("srate", "Silver", 120), ("prate", "Platinum", 120)])
                self.grid_widget.set_rows([{"tdate": r.get("tdate", ""), "grate": f'{r.get("grate", 0):.2f}',
                                            "g18rate": f'{r.get("g18rate", 0):.2f}', "srate": f'{r.get("srate", 0):.2f}',
                                            "prate": f'{r.get("prate", 0):.2f}'} for r in rows])
                self.summary.configure(text=f"{len(rows)} rate day(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
