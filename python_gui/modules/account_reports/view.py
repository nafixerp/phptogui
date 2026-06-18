"""Account Reports window — Chart of Accounts / Group Summary / Cash Balance."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import AccountReportsService

_MODES = ["Chart of Accounts", "Group Summary", "Cash Balance"]
_TYPES = ["All", "Assets Only", "Liabilities Only", "Expenses Only", "Incomes Only"]


class AccountReportsView(ctk.CTkFrame):
    TITLE = "Account Reports"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = AccountReportsService(database, gilevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.mode = ctk.CTkOptionMenu(head, width=170, values=_MODES, command=lambda _v: self._show()); self.mode.pack(side="left", padx=10)
        self.type = ctk.CTkOptionMenu(head, width=140, values=_TYPES); self.type.pack(side="left", padx=4)
        ctk.CTkLabel(head, text="As on").pack(side="left", padx=(8, 4))
        self.asof = ctk.CTkEntry(head, width=110); self.asof.pack(side="left"); self.asof.insert(0, date.today().isoformat())
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
            if m == "Chart of Accounts":
                rows = self.service.chart_of_accounts(self.asof.get(), self.type.get())
                self._set_cols([("accode", "Code", 110), ("acname", "Account", 200), ("group_name", "Group", 150),
                                ("debit", "Debit", 120), ("credit", "Credit", 120)])
                self.grid_widget.set_rows([{"accode": r["accode"], "acname": r["acname"], "group_name": r["group_name"],
                                            "debit": f'{r["debit"]:.2f}', "credit": f'{r["credit"]:.2f}'} for r in rows])
                self.summary.configure(text=f"{len(rows)} account(s).", text_color=("gray20", "gray80"))
            elif m == "Group Summary":
                rows = self.service.group_summary(self.asof.get(), self.type.get())
                self._set_cols([("group", "Group", 240), ("count", "Accounts", 90), ("debit", "Debit", 130), ("credit", "Credit", 130)])
                self.grid_widget.set_rows([{"group": r["group"], "count": r["count"], "debit": f'{r["debit"]:.2f}',
                                            "credit": f'{r["credit"]:.2f}'} for r in rows])
                self.summary.configure(text=f"{len(rows)} group(s).", text_color=("gray20", "gray80"))
            else:
                bal = self.service.cash_balance(self.asof.get())
                self._set_cols([("k", "Measure", 220), ("v", "Amount", 200)])
                self.grid_widget.set_rows([{"k": "Cash Balance", "v": f"{bal:.2f}"}])
                self.summary.configure(text=f"Cash balance as on {self.asof.get()}: {bal:.2f}", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
