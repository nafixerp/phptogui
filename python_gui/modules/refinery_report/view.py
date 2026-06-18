"""Refinery Report window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import RefineryReportService

_STATUS = {"All": "", "Forward": "1", "Return": "2"}


class RefineryReportView(ctk.CTkFrame):
    TITLE = "Refinery Report"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = RefineryReportService(database, gilevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(16, 4))
        self.d1 = ctk.CTkEntry(head, width=110); self.d1.pack(side="left"); self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(8, 4))
        self.d2 = ctk.CTkEntry(head, width=110); self.d2.pack(side="left"); self.d2.insert(0, date.today().isoformat())
        self.status_f = ctk.CTkOptionMenu(head, width=100, values=list(_STATUS)); self.status_f.pack(side="left", padx=8)
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[
            ("tdate", "Date", 100), ("docno", "Doc No", 100), ("status_lbl", "Type", 80),
            ("refinername", "Refiner", 150), ("itemname", "Item", 140),
            ("issuedwgt", "Issued", 100), ("rcvdwgt", "Received", 100), ("touch", "Touch", 80)], key_field="_k")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._show()

    def _show(self):
        try:
            rows = self.service.report(self.d1.get(), self.d2.get(), status=_STATUS[self.status_f.get()])
            self.grid_widget.set_rows([{
                "_k": i, "tdate": r["tdate"], "docno": r["docno"], "status_lbl": r["status_lbl"],
                "refinername": r["refinername"], "itemname": r["itemname"],
                "issuedwgt": f'{r["issuedwgt"]:.3f}', "rcvdwgt": f'{r["rcvdwgt"]:.3f}',
                "touch": f'{r["touch"]:.2f}'} for i, r in enumerate(rows)])
            self.summary.configure(text=f"{len(rows)} row(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
