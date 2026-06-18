"""Gold Loan window — list loans and inspect pledged items + collections."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import GoldLoanService


class GoldLoanView(ctk.CTkFrame):
    TITLE = "Gold Loan"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = GoldLoanService(database, gilevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1); self.grid_rowconfigure(3, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.open_only = ctk.CTkCheckBox(head, text="Open only", command=self._reload); self.open_only.pack(side="left", padx=16)
        ctk.CTkButton(head, text="Show", width=70, command=self._reload).pack(side="left", padx=8)
        self.loans = DataGrid(self, columns=[("docno", "Doc No", 110), ("tdate", "Date", 100), ("cname", "Customer", 180),
                              ("loanamt", "Loan Amt", 120), ("closed", "Closed", 70)], on_select=self._on_select, key_field="slno")
        self.loans.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        ctk.CTkLabel(self, text="Pledged items & collections", anchor="w").grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 0))
        self.detail = DataGrid(self, columns=[("kind", "Kind", 100), ("a", "Ref/Item", 160), ("b", "Date/Wt", 120), ("amount", "Amount", 120)], key_field="_k")
        self.detail.grid(row=3, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=4, column=0, sticky="ew", padx=14, pady=4)
        self._reload()

    def _reload(self):
        try:
            rows = self.service.list(only_open=bool(self.open_only.get()))
            self.loans.set_rows([{"slno": r.get("slno"), "docno": str(r.get("docno") or ""), "tdate": str(r.get("tdate") or ""),
                                  "cname": str(r.get("cname") or ""), "loanamt": f'{float(r.get("loanamt") or 0):.2f}',
                                  "closed": str(r.get("closed") or "")} for r in rows])
            self.status.configure(text=f"{len(rows)} loan(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        try:
            data = self.service.load(row.get("slno"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        out = []; k = 0
        if data:
            for it in data["items"]:
                k += 1
                out.append({"_k": k, "kind": "Item", "a": str(it.get("name") or it.get("code") or ""),
                            "b": f'{float(it.get("weight") or 0):.3f}', "amount": f'{float(it.get("amount") or 0):.2f}'})
            for c in data["collections"]:
                k += 1
                out.append({"_k": k, "kind": "Collection", "a": str(c.get("docno") or ""),
                            "b": str(c.get("tdate") or ""), "amount": f'{float(c.get("amount") or 0):.2f}'})
            self.status.configure(text=f'Balance: {data["balance"]:.2f}', text_color=("gray20", "gray80"))
        self.detail.set_rows(out)
