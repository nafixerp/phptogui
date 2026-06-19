"""Amount <-> Weight Transfer window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import AmtWgtTransferError, AmtWgtTransferService


class AmtWgtTransferView(ctk.CTkFrame):
    TITLE = "Amount / Weight Transfer"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = AmtWgtTransferService(PostingEngine(database), session, control=getattr(session, "gilevel", 1))
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        ctk.CTkLabel(self, text="Type").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.ttype = ctk.CTkOptionMenu(self, width=160, values=["Amt To Wgt", "Wgt To Amt"]); self.ttype.grid(row=1, column=1, sticky="w", padx=12, pady=4)
        self.fields: dict[str, ctk.CTkEntry] = {}
        for i, (key, label, dflt) in enumerate([("code", "Party Code", ""), ("amt", "Amount", "0"),
                                                ("rate", "Rate", "0"), ("weight", "Weight", "0")], start=2):
            ctk.CTkLabel(self, text=label).grid(row=i, column=0, sticky="w", padx=12, pady=4)
            e = ctk.CTkEntry(self, width=180); e.grid(row=i, column=1, sticky="w", padx=12, pady=4)
            if dflt:
                e.insert(0, dflt)
            self.fields[key] = e
        ctk.CTkButton(self, text="Save", width=110, command=self._save).grid(row=6, column=1, sticky="w", padx=12, pady=10)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=7, column=0, columnspan=2, sticky="ew", padx=14, pady=4)

    def _save(self):
        f = {k: e.get() for k, e in self.fields.items()}
        try:
            res = self.service.save(tdate=date.today().isoformat(), code=f["code"], amt=f["amt"] or 0,
                                    weight=f["weight"] or 0, rate=f["rate"] or 0, ttype=self.ttype.get())
        except (AmtWgtTransferError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=f'Saved {res["docno"]} (slno {res["slno"]})', text_color="#1E8449")
