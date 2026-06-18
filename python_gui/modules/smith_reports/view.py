"""Smith Reports window — Transaction Summary / W&A Summary."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import SmithReportsService

_MODES = ["Transaction Summary", "W&A Summary"]
_CTYPE = {"Goldsmith": "G", "Jeweller": "J"}


class SmithReportsView(ctk.CTkFrame):
    TITLE = "Smith Reports"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = SmithReportsService(database, rlevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.mode = ctk.CTkOptionMenu(head, width=180, values=_MODES, command=lambda _v: self._show()); self.mode.pack(side="left", padx=10)
        self.ctype = ctk.CTkOptionMenu(head, width=110, values=list(_CTYPE)); self.ctype.pack(side="left", padx=4)
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
        ct = _CTYPE[self.ctype.get()]
        try:
            if self.mode.get() == "Transaction Summary":
                rows = self.service.trans_summary(self.d1.get(), self.d2.get(), ctype=ct)
                self._set_cols([("name", "Smith", 180), ("issuedwgt", "Issued", 100), ("rcvdwgt", "Received", 100),
                                ("pendwgt", "Pending", 100), ("wastage", "Wastage", 100), ("mcstamt", "MC+Stone", 120)])
                self.grid_widget.set_rows([{"name": r["name"], "issuedwgt": f'{r["issuedwgt"]:.3f}', "rcvdwgt": f'{r["rcvdwgt"]:.3f}',
                                            "pendwgt": f'{r["pendwgt"]:.3f}', "wastage": f'{r["wastage"]:.3f}', "mcstamt": f'{r["mcstamt"]:.2f}'} for r in rows])
            else:
                rows = self.service.wa_summary(self.d2.get(), ctype=ct)
                self._set_cols([("name", "Smith", 180), ("issuedwgt", "Issued", 110), ("rcvdwgt", "Received", 110),
                                ("pendwgt", "Pending", 110), ("lastissue", "Last Issue", 110), ("tranamt", "Cash Bal", 120)])
                self.grid_widget.set_rows([{"name": r["name"], "issuedwgt": f'{r["issuedwgt"]:.3f}', "rcvdwgt": f'{r["rcvdwgt"]:.3f}',
                                            "pendwgt": f'{r["pendwgt"]:.3f}', "lastissue": r["lastissue"], "tranamt": f'{r["tranamt"]:.2f}'} for r in rows])
            self.summary.configure(text=f"{len(rows)} smith(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
