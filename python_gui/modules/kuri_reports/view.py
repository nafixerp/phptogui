"""Kuri Reports window — Finish/Maturity list and Interest-Post list."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import KuriReportsService

_MODES = ["Finish / Maturity", "Interest Post"]


class KuriReportsView(ctk.CTkFrame):
    TITLE = "Kuri Finish / Interest"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = KuriReportsService(database, control=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.mode = ctk.CTkOptionMenu(head, width=160, values=_MODES, command=lambda _v: self._show()); self.mode.pack(side="left", padx=10)
        ctk.CTkLabel(head, text="As on").pack(side="left", padx=(8, 4))
        self.tdate = ctk.CTkEntry(head, width=110); self.tdate.pack(side="left"); self.tdate.insert(0, date.today().isoformat())
        ctk.CTkLabel(head, text="Rate").pack(side="left", padx=(8, 4))
        self.rate = ctk.CTkEntry(head, width=90); self.rate.pack(side="left"); self.rate.insert(0, "0")
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("a", "", 100)], key_field="a"); self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._show()

    def _set_cols(self, cols):
        self.grid_widget.destroy()
        self.grid_widget = DataGrid(self, columns=cols, key_field=cols[0][0]); self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _show(self):
        try:
            if self.mode.get() == "Finish / Maturity":
                rows = self.service.finish_list(self.tdate.get(), self.rate.get())
                self._set_cols([("code", "Code", 100), ("name", "Member", 180), ("totamt", "Total", 110),
                                ("tcolln", "Collected", 110), ("balance", "Balance", 110), ("estwgt", "Est Wt", 100)])
                self.grid_widget.set_rows([{"code": r["code"], "name": r["name"], "totamt": f'{r["totamt"]:.2f}',
                                            "tcolln": f'{r["tcolln"]:.2f}', "balance": f'{r["balance"]:.2f}', "estwgt": f'{r["estwgt"]:.3f}'} for r in rows])
            else:
                rows = self.service.interest_list(self.tdate.get())
                self._set_cols([("code", "Code", 100), ("name", "Member", 200), ("tcolln", "Collected", 120),
                                ("intrate", "Int %", 90), ("intamt", "Interest", 120)])
                self.grid_widget.set_rows([{"code": r["code"], "name": r["name"], "tcolln": f'{r["tcolln"]:.2f}',
                                            "intrate": f'{r["intrate"]:.3f}', "intamt": f'{r["intamt"]:.2f}'} for r in rows])
            self.summary.configure(text=f"{len(rows)} member(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
