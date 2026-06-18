"""Party outstanding-balance report window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import PartyReportsService

_TYPES = ["C", "S", "G", "R", "J", "F", "D"]


class PartyReportsView(ctk.CTkFrame):
    TITLE = "Party Outstanding"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PartyReportsService(database, rlevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Type").pack(side="left", padx=(16, 4))
        self.ctype = ctk.CTkOptionMenu(head, width=80, values=_TYPES, command=lambda _v: self._show()); self.ctype.pack(side="left")
        self.search = ctk.StringVar()
        e = ctk.CTkEntry(head, width=180, placeholder_text="Search…", textvariable=self.search); e.pack(side="right")
        e.bind("<Return>", lambda _ev: self._show())
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="right", padx=6)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[("code", "Code", 100), ("name", "Name", 220),
                                    ("balance", "Balance", 120), ("side", "Dr/Cr", 60)], key_field="code")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._show()

    def _show(self):
        try:
            res = self.service.outstanding(self.ctype.get(), self.search.get())
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        rows = [{"code": r["code"], "name": r["name"], "balance": f'{r["balance"]:.2f}', "side": r["side"]} for r in res["rows"]]
        self.grid_widget.set_rows(rows)
        self.summary.configure(text=f"Parties: {len(rows)}    Total Dr: {res['total_dr']:.2f}    Total Cr: {res['total_cr']:.2f}",
                               text_color=("gray20", "gray80"))
