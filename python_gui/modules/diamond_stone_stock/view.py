"""Diamond / Stone Stock window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import DiamondStoneStockService

_TYPES = ["All", "Diamond", "Platinum", "Color Stone"]


class DiamondStoneStockView(ctk.CTkFrame):
    TITLE = "Diamond / Stone Stock"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = DiamondStoneStockService(database, gilevel=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.type = ctk.CTkOptionMenu(head, width=130, values=_TYPES, command=lambda _v: self._show()); self.type.pack(side="left", padx=10)
        ctk.CTkButton(head, text="Show", width=70, command=self._show).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(self, text="", anchor="w"); self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        self.grid_widget = DataGrid(self, columns=[
            ("code", "Item", 110), ("name", "Name", 200), ("nos", "Nos", 70),
            ("grosswgt", "Gross Wt", 110), ("goldwgt", "Gold Wt", 110),
            ("stonewgt", "Stone Wt", 110), ("dmdwgt", "Diamond Ct", 110)], key_field="code")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._show()

    def _show(self):
        try:
            rows = self.service.summary(self.type.get())
            self.grid_widget.set_rows([{
                "code": r["code"], "name": r["name"], "nos": r["nos"],
                "grosswgt": f'{r["grosswgt"]:.3f}', "goldwgt": f'{r["goldwgt"]:.3f}',
                "stonewgt": f'{r["stonewgt"]:.3f}', "dmdwgt": f'{r["dmdwgt"]:.3f}'} for r in rows])
            self.summary.configure(text=f"{len(rows)} item(s) in stock.", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.summary.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
