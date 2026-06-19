"""Order Sale window — convert an order into a sale bill."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from .service import OrderSaleError, OrderSalePostingService

_ITEM_FIELDS = [("item_code", "Item"), ("qty", "Qty"), ("weight", "Weight"),
                ("stonewgt", "Stone"), ("making_charge", "MC"), ("amount", "Amount"), ("stktype", "Stk Type")]


class OrderSaleView(ctk.CTkFrame):
    TITLE = "Order Sale"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = OrderSalePostingService(PostingEngine(database), session, control=getattr(session, "gilevel", 1))
        self._items: list[dict] = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(3, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="Save Sale", width=110, command=self._save).pack(side="right", padx=6)
        hdr = ctk.CTkFrame(self, fg_color="transparent"); hdr.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        self.header: dict[str, ctk.CTkEntry] = {}
        for key, label, dflt in [("order_no", "Order No", ""), ("customer_code", "Cust Code", ""),
                                 ("customer_name", "Customer", ""), ("cashbank_code", "Cash/Bank", "CASH"),
                                 ("bill_total", "Bill Total", "0"), ("net_total", "Net Total", "0"),
                                 ("discount", "Discount", "0"), ("tax", "Tax", "0"),
                                 ("advance", "Order Adv", "0"), ("received", "Received", "0")]:
            ctk.CTkLabel(hdr, text=label).pack(side="left", padx=(6, 2))
            e = ctk.CTkEntry(hdr, width=88); e.pack(side="left")
            if dflt:
                e.insert(0, dflt)
            self.header[key] = e
        entry = ctk.CTkFrame(self, fg_color="transparent"); entry.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        self.inputs: dict[str, ctk.CTkEntry] = {}
        for key, label in _ITEM_FIELDS:
            ctk.CTkLabel(entry, text=label).pack(side="left", padx=(6, 2))
            e = ctk.CTkEntry(entry, width=80); e.pack(side="left"); self.inputs[key] = e
        ctk.CTkButton(entry, text="Add Item", width=80, command=self._add).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=[(k, lbl, 90) for k, lbl in _ITEM_FIELDS], key_field="item_code")
        self.grid_widget.grid(row=3, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=4, column=0, sticky="ew", padx=14, pady=4)

    def _add(self):
        row = {k: (e.get() or "").strip() for k, e in self.inputs.items()}
        if not row.get("item_code"):
            self.status.configure(text="Item code required.", text_color="#C0392B"); return
        self._items.append(row); self.grid_widget.set_rows(self._items)
        for e in self.inputs.values():
            e.delete(0, "end")

    def _save(self):
        amounts = {k: e.get() for k, e in self.header.items()}
        try:
            res = self.service.post(amounts=amounts, items=self._items, billdate=date.today().isoformat(),
                                    order_no=amounts.get("order_no", ""))
        except (OrderSaleError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._items = []; self.grid_widget.set_rows([])
        bal = "balanced" if res["balanced"] else "rounded"
        self.status.configure(text=f'Saved {res["bill_no"]} (slno {res["slno"]}, {bal})', text_color="#1E8449")
