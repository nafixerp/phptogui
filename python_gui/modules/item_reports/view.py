"""Item Reports window — Itemwise Profit / Item Movement / Cost List."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import ItemReportsService

_MODES = ["Itemwise Profit", "Item Movement", "Cost List"]


class ItemReportsView(ctk.CTkFrame):
    TITLE = "Item Reports"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = ItemReportsService(database, rlevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.mode = ctk.CTkOptionMenu(head, width=160, values=_MODES, command=lambda _v: self._show()); self.mode.pack(side="left", padx=10)
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
        m = self.mode.get()
        try:
            if m == "Itemwise Profit":
                res = self.service.itemwise_profit(self.d1.get(), self.d2.get())
                self._set_cols([("code", "Code", 110), ("name", "Item", 200), ("tqty", "Qty", 70),
                                ("twgt", "Weight", 100), ("saleamt", "Sale", 120), ("costamt", "Cost", 120), ("profit", "Profit", 120)])
                self.grid_widget.set_rows([{"code": r["code"], "name": r["name"], "tqty": r["tqty"], "twgt": f'{r["twgt"]:.3f}',
                                            "saleamt": f'{r["saleamt"]:.2f}', "costamt": f'{r["costamt"]:.2f}', "profit": f'{r["profit"]:.2f}'} for r in res["rows"]])
                t = res["totals"]; self.summary.configure(text=f'{t["count"]} item(s)  ·  Profit {t["profit"]:.2f}', text_color=("gray20", "gray80"))
            elif m == "Item Movement":
                rows = self.service.item_movement(self.d1.get(), self.d2.get())
                self._set_cols([("icode", "Code", 110), ("iname", "Item", 220), ("tot_qty", "Qty", 90),
                                ("tot_wgt", "Weight", 120), ("tot_amt", "Amount", 140)])
                self.grid_widget.set_rows([{"icode": r["icode"], "iname": r["iname"], "tot_qty": r["tot_qty"],
                                            "tot_wgt": f'{r["tot_wgt"]:.3f}', "tot_amt": f'{r["tot_amt"]:.2f}'} for r in rows])
                self.summary.configure(text=f"{len(rows)} item(s).", text_color=("gray20", "gray80"))
            else:
                rows = self.service.cost_list()
                self._set_cols([("code", "Code", 120), ("name", "Item", 240), ("itype", "Type", 70),
                                ("cost", "Cost", 130), ("rate", "Rate", 130)])
                self.grid_widget.set_rows([{"code": r["code"], "name": r["name"], "itype": r["itype"],
                                            "cost": f'{r["cost"]:.2f}', "rate": f'{r["rate"]:.2f}'} for r in rows])
                self.summary.configure(text=f"{len(rows)} item(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
