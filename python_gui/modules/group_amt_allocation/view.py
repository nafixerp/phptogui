"""Group Amount Allocation window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from ..widgets.datagrid import DataGrid
from .service import GroupAmtAllocationError, GroupAmtAllocationService


class GroupAmtAllocationView(ctk.CTkFrame):
    TITLE = "Group Amount Allocation"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = GroupAmtAllocationService(PostingEngine(database), session, control=getattr(session, "gilevel", 1))
        self._items: list[dict] = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Opp A/c").pack(side="left", padx=(16, 4))
        self.opac = ctk.CTkEntry(head, width=110); self.opac.pack(side="left")
        self.credited = ctk.CTkOptionMenu(head, width=110, values=["Credited", "Debited"]); self.credited.pack(side="left", padx=8)
        ctk.CTkButton(head, text="Save", width=90, command=self._save).pack(side="right", padx=6)
        entry = ctk.CTkFrame(self, fg_color="transparent"); entry.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkLabel(entry, text="Account").pack(side="left", padx=(6, 2))
        self.acc = ctk.CTkEntry(entry, width=120); self.acc.pack(side="left")
        ctk.CTkLabel(entry, text="Amount").pack(side="left", padx=(8, 2))
        self.amt = ctk.CTkEntry(entry, width=110); self.amt.pack(side="left")
        ctk.CTkButton(entry, text="Add", width=60, command=self._add).pack(side="left", padx=8)
        self.grid_widget = DataGrid(self, columns=[("accode", "Account", 200), ("amount", "Amount", 160)], key_field="accode")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=3, column=0, sticky="ew", padx=14, pady=4)

    def _add(self):
        ac = (self.acc.get() or "").strip(); amt = (self.amt.get() or "").strip()
        if not ac or not amt:
            self.status.configure(text="Account and amount required.", text_color="#C0392B"); return
        self._items.append({"accode": ac, "amount": amt}); self.grid_widget.set_rows(self._items)
        self.acc.delete(0, "end"); self.amt.delete(0, "end")

    def _save(self):
        if not self._items:
            self.status.configure(text="No allocations.", text_color="#C0392B"); return
        try:
            res = self.service.save(tdate=date.today().isoformat(), opac=self.opac.get(),
                                    items=self._items, credited=self.credited.get() == "Credited")
        except (GroupAmtAllocationError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._items = []; self.grid_widget.set_rows([])
        self.status.configure(text=f'Saved {res["docno"]} (total {res["total"]:.2f})', text_color="#1E8449")
