"""Rate-Difference Adjustment window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import RateDiffError, RateDiffService


class RateDiffView(ctk.CTkFrame):
    TITLE = "Rate Difference Adjustment"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = RateDiffService(PostingEngine(database), session, control=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        ctk.CTkLabel(self, text="Date", anchor="w").grid(row=1, column=0, sticky="w", padx=12, pady=3)
        self.tdate = ctk.CTkEntry(self, width=200); self.tdate.grid(row=1, column=1, sticky="w", padx=12, pady=3); self.tdate.insert(0, date.today().isoformat())
        self.fields: dict[str, ctk.CTkEntry] = {}
        for i, (key, label, dflt) in enumerate([("code", "Party Code", ""), ("billno", "Bill No (opt)", ""),
                                                ("weight", "Weight", "0"), ("newrate", "New Rate", "0"),
                                                ("diffamt", "Diff Amount", "0")], start=2):
            ctk.CTkLabel(self, text=label, anchor="w").grid(row=i, column=0, sticky="w", padx=12, pady=3)
            e = ctk.CTkEntry(self, width=200); e.grid(row=i, column=1, sticky="w", padx=12, pady=3)
            if dflt:
                e.insert(0, dflt)
            self.fields[key] = e
        ctk.CTkButton(self, text="Save", width=120, command=self._save).grid(row=8, column=1, sticky="w", padx=12, pady=10)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=9, column=0, columnspan=2, sticky="ew", padx=14, pady=4)

    def _save(self):
        f = {k: e.get() for k, e in self.fields.items()}
        try:
            res = self.service.save(tdate=self.tdate.get(), code=f["code"], diffamt=f["diffamt"] or 0,
                                    billno=f["billno"], weight=f["weight"] or 0, newrate=f["newrate"] or 0)
        except (RateDiffError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=f'Saved {res["docno"]} (slno {res["slno"]})', text_color="#1E8449")
