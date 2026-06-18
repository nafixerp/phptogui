"""Purity Certificate window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import PurityCertificateService


class PurityCertificateView(ctk.CTkFrame):
    TITLE = "Purity Certificate"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PurityCertificateService(database)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        try:
            ctk.CTkLabel(head, text=f"Next Cert No: {self.service.next_cert_no()}").pack(side="left", padx=16)
        except Exception:
            pass
        ctk.CTkLabel(head, text="Item").pack(side="left", padx=(8, 4))
        self.q = ctk.CTkEntry(head, width=160); self.q.pack(side="left")
        ctk.CTkButton(head, text="Search", width=70, command=self._search).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=[("code", "Code", 120), ("name", "Name", 280)], key_field="code")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=4)

    def _search(self):
        try:
            rows = self.service.search_items(self.q.get())
            self.grid_widget.set_rows([{"code": str(r.get("code") or ""), "name": str(r.get("name") or "")} for r in rows])
            self.status.configure(text=f"{len(rows)} item(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
