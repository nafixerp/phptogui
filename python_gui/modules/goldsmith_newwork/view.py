"""Goldsmith New-Work Note window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import GoldsmithNewWorkService

_TYPES = {"All": "", "New Work": "new-work", "In Progress": "work-in-progress",
          "Finished": "work-finished", "Pending": "pending"}
_STATUS_LBL = {1: "New", 2: "WIP", 3: "Finished"}


class GoldsmithNewWorkView(ctk.CTkFrame):
    TITLE = "Goldsmith New-Work Note"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = GoldsmithNewWorkService(database)
        self._sel = None
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.type = ctk.CTkOptionMenu(head, width=130, values=list(_TYPES), command=lambda _v: self._reload()); self.type.pack(side="left", padx=10)
        ctk.CTkLabel(head, text="Smith").pack(side="left", padx=(8, 4))
        self.smith = ctk.CTkEntry(head, width=120); self.smith.pack(side="left")
        ctk.CTkButton(head, text="Show", width=70, command=self._reload).pack(side="left", padx=8)
        ctk.CTkButton(head, text="Delete Selected", width=120, command=self._delete).pack(side="right", padx=6)
        self.grid_widget = DataGrid(self, columns=[("tdate", "Date", 100), ("smithname", "Smith", 160), ("itemname", "Item", 160),
                                    ("ordno", "Order", 100), ("qty", "Qty", 60), ("weight", "Weight", 100), ("status_lbl", "Status", 90)],
                                    on_select=self._on_select, key_field="sno")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=2, column=0, sticky="ew", padx=14, pady=4)
        self._reload()

    def _reload(self):
        try:
            rows = self.service.list(_TYPES[self.type.get()], self.smith.get())
            self.grid_widget.set_rows([{"sno": r.get("sno"), "tdate": str(r.get("tdate") or ""),
                                        "smithname": str(r.get("smithname") or r.get("smithcode") or ""),
                                        "itemname": str(r.get("itemname") or r.get("icode") or ""),
                                        "ordno": str(r.get("ordno") or ""), "qty": r.get("qty") or 0,
                                        "weight": f'{float(r.get("weight") or 0):.3f}',
                                        "status_lbl": _STATUS_LBL.get(int(r.get("status") or 1), "New")} for r in rows])
            self.status.configure(text=f"{len(rows)} note(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        self._sel = row.get("sno")

    def _delete(self):
        if not self._sel:
            self.status.configure(text="Select a row.", text_color="#C0392B"); return
        try:
            self.service.delete(self._sel)
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text="Deleted.", text_color="#1E8449")
