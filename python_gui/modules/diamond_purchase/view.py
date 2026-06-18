"""Diamond Purchase register — list bills and inspect item + stone detail."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import DiamondPurchaseService


class DiamondPurchaseView(ctk.CTkFrame):
    TITLE = "Diamond Purchase"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = DiamondPurchaseService(database, rlevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1); self.grid_rowconfigure(3, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="From").pack(side="left", padx=(16, 4))
        self.d1 = ctk.CTkEntry(head, width=110); self.d1.pack(side="left"); self.d1.insert(0, date.today().replace(month=1, day=1).isoformat())
        ctk.CTkLabel(head, text="To").pack(side="left", padx=(8, 4))
        self.d2 = ctk.CTkEntry(head, width=110); self.d2.pack(side="left"); self.d2.insert(0, date.today().isoformat())
        ctk.CTkButton(head, text="Show", width=70, command=self._reload).pack(side="left", padx=8)
        try:
            ctk.CTkLabel(head, text=f"Next Doc: {self.service.next_doc_no()}").pack(side="right", padx=8)
        except Exception:
            pass
        self.bills = DataGrid(self, columns=[("docno", "Doc No", 110), ("billno", "Bill No", 110), ("tdate", "Date", 100),
                              ("name", "Supplier", 200), ("netamt", "Net Amt", 120)], on_select=self._on_select, key_field="docno")
        self.bills.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        ctk.CTkLabel(self, text="Items / Stone detail", anchor="w").grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 0))
        self.detail = DataGrid(self, columns=[("code", "Item/Stone", 140), ("kind", "Type", 80), ("qty", "Qty/Pcs", 90),
                               ("weight", "Wgt/Carat", 110), ("rate", "Rate", 100), ("amount", "Amount", 120)], key_field="_k")
        self.detail.grid(row=3, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=4, column=0, sticky="ew", padx=14, pady=4)
        self._reload()

    def _reload(self):
        try:
            rows = self.service.list_bills(self.d1.get(), self.d2.get())
            self.bills.set_rows([{"docno": str(r.get("docno") or ""), "billno": str(r.get("billno") or ""),
                                  "tdate": str(r.get("tdate") or ""), "name": str(r.get("name") or ""),
                                  "netamt": f'{float(r.get("netamt") or 0):.2f}'} for r in rows])
            self.status.configure(text=f"{len(rows)} bill(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        try:
            bill = self.service.get_bill(row.get("docno", ""))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        out = []; k = 0
        if bill:
            for it in bill["items"]:
                k += 1
                out.append({"_k": k, "code": str(it.get("code") or ""), "kind": "Item",
                            "qty": str(it.get("qty") or 0), "weight": f'{float(it.get("weight") or 0):.3f}',
                            "rate": f'{float(it.get("rate") or 0):.2f}', "amount": f'{float(it.get("amount") or 0):.2f}'})
                for d in it.get("dmd_rows", []):
                    k += 1
                    out.append({"_k": k, "code": f'  · {d["stcode"]}', "kind": d.get("sttype") or "Stone",
                                "qty": str(d.get("pcs") or 0), "weight": f'{float(d.get("carats") or 0):.3f}',
                                "rate": f'{float(d.get("rate") or 0):.2f}', "amount": f'{float(d.get("amount") or 0):.2f}'})
        self.detail.set_rows(out)
