"""Reorder Levels window — view/edit per-item reorder bands."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import ReorderError, ReorderService


class ReorderView(ctk.CTkFrame):
    TITLE = "Reorder Levels"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = ReorderService(database)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="Item Code").pack(side="left", padx=(16, 4))
        self.code = ctk.CTkEntry(head, width=140); self.code.pack(side="left")
        ctk.CTkButton(head, text="Load", width=70, command=self._load).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[
            ("model", "Model", 120), ("size", "Size", 100), ("weight1", "Wt From", 110),
            ("weight2", "Wt To", 110), ("minqty", "Min Qty", 90), ("maxqty", "Max Qty", 90)], key_field="_k")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)

    def _load(self):
        try:
            res = self.service.get_item(self.code.get())
        except ReorderError as exc:
            self.summary.configure(text=str(exc), text_color="#C0392B"); return
        if not res:
            self.grid_widget.set_rows([]); self.summary.configure(text="Item not found.", text_color="#C0392B"); return
        levels = res["levels"]
        self.grid_widget.set_rows([{
            "_k": i, "model": str(lv.get("model") or ""), "size": str(lv.get("size") or ""),
            "weight1": f'{float(lv.get("weight1") or 0):.3f}', "weight2": f'{float(lv.get("weight2") or 0):.3f}',
            "minqty": lv.get("minqty") or 0, "maxqty": lv.get("maxqty") or 0} for i, lv in enumerate(levels)])
        self.summary.configure(text=f'{res["item"].get("name") or ""}: {len(levels)} band(s).', text_color=("gray20", "gray80"))
