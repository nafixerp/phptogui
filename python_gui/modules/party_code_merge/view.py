"""Party Code Merge window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from .service import PartyCodeMergeError, PartyCodeMergeService


class PartyCodeMergeView(ctk.CTkFrame):
    TITLE = "Party Code Merge"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PartyCodeMergeService(database, session)
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        ctk.CTkLabel(self, text="Source codes (comma-sep)").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.sources = ctk.CTkEntry(self, width=260); self.sources.grid(row=1, column=1, sticky="w", padx=12, pady=4)
        ctk.CTkLabel(self, text="Target code").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        self.target = ctk.CTkEntry(self, width=180); self.target.grid(row=2, column=1, sticky="w", padx=12, pady=4)
        self.delete_src = ctk.CTkCheckBox(self, text="Delete source masters after merge")
        self.delete_src.grid(row=3, column=1, sticky="w", padx=12, pady=6); self.delete_src.select()
        ctk.CTkButton(self, text="Merge", width=120, fg_color="#922B21", hover_color="#7B241C", command=self._merge).grid(row=4, column=1, sticky="w", padx=12, pady=10)
        self.status = ctk.CTkLabel(self, text="Warning: merge re-keys data across many tables and cannot be undone.",
                                   anchor="w", text_color="#C0392B"); self.status.grid(row=5, column=0, columnspan=2, sticky="ew", padx=14, pady=4)

    def _merge(self):
        srcs = [s for s in (self.sources.get() or "").replace(";", ",").split(",") if s.strip()]
        try:
            res = self.service.merge(srcs, self.target.get(), delete_sources=bool(self.delete_src.get()))
        except (PartyCodeMergeError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(
            text=f'Merged into {res["target"]}: {res["reference_rows_updated"]} reference row(s) updated, '
                 f'{res["opening_balances_moved"]} opening balance(s) moved.', text_color="#1E8449")
