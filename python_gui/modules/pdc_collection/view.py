"""PDC Collection / Clearance window — clear a post-dated cheque."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ...core.posting import PostingEngine
from .service import PdcCollectionError, PdcCollectionService


class PdcCollectionView(ctk.CTkFrame):
    TITLE = "PDC Collection"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PdcCollectionService(PostingEngine(database), session)
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        self.fields: dict[str, ctk.CTkEntry] = {}
        spec = [("chequeno", "Cheque No"), ("party_code", "Party Code"), ("bank", "Bank Code"),
                ("amount", "Amount"), ("expense", "Bank Expense"), ("scharge", "Service Charge"),
                ("net_amount", "Net Amount"), ("sidocno", "PDC Doc No")]
        for i, (key, label) in enumerate(spec, start=1):
            ctk.CTkLabel(self, text=label, anchor="w").grid(row=i, column=0, sticky="w", padx=12, pady=3)
            e = ctk.CTkEntry(self, width=200); e.grid(row=i, column=1, sticky="w", padx=12, pady=3)
            if key in ("amount", "expense", "scharge", "net_amount"):
                e.insert(0, "0")
            self.fields[key] = e
        ctk.CTkLabel(self, text="Date", anchor="w").grid(row=9, column=0, sticky="w", padx=12, pady=3)
        self.tdate = ctk.CTkEntry(self, width=200); self.tdate.grid(row=9, column=1, sticky="w", padx=12, pady=3); self.tdate.insert(0, date.today().isoformat())
        self.bounce = ctk.CTkCheckBox(self, text="Bounce"); self.bounce.grid(row=10, column=1, sticky="w", padx=12, pady=6)
        ctk.CTkButton(self, text="Save Clearance", width=140, command=self._save).grid(row=11, column=1, sticky="w", padx=12, pady=10)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=12, column=0, columnspan=2, sticky="ew", padx=14, pady=4)

    def _save(self):
        f = {k: e.get() for k, e in self.fields.items()}
        try:
            res = self.service.collect(
                chequeno=f["chequeno"], tdate=self.tdate.get(), party_code=f["party_code"], bank=f["bank"],
                amount=f["amount"] or 0, net_amount=f["net_amount"] or 0, expense=f["expense"] or 0,
                scharge=f["scharge"] or 0, bounce=bool(self.bounce.get()), sidocno=f["sidocno"])
        except (PdcCollectionError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        bal = "balanced" if res["balanced"] else "UNBALANCED"
        self.status.configure(text=f'Saved {res["vchno"]} (slno {res["slno"]}, {bal})', text_color="#1E8449")
