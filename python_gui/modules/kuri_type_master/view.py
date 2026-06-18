"""Kuri Type Master window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import KuriTypeMasterService


class KuriTypeMasterView(ctk.CTkFrame):
    TITLE = "Kuri Type Master"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = KuriTypeMasterService(database)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="Reload", width=70, command=self._reload).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=[
            ("code", "Code", 90), ("name", "Name", 180), ("instnos", "Insts", 70),
            ("instamt", "Inst Amt", 100), ("totamt", "Total", 110), ("bonus", "Bonus", 90),
            ("colntype", "Type", 70)], key_field="code")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=4)
        self._reload()

    def _reload(self):
        try:
            rows = self.service.load()
            self.grid_widget.set_rows([{
                "code": str(r.get("code") or ""), "name": str(r.get("name") or ""),
                "instnos": r.get("instnos") or 0, "instamt": f'{float(r.get("instamt") or 0):.2f}',
                "totamt": f'{float(r.get("totamt") or 0):.2f}', "bonus": f'{float(r.get("bonus") or 0):.2f}',
                "colntype": str(r.get("colntype") or "")} for r in rows])
            self.status.configure(text=f"{len(rows)} type(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
