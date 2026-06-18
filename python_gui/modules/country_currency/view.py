"""Country / Currency settings window."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from .service import CountryCurrencyService

_F = ["country_code", "country_name", "religion", "currency_code", "currency_symbol",
      "currency_name", "base_currency", "exchange_rate", "date_format", "weight_unit",
      "purity_system", "tax_label", "number_format", "decimal_places"]


class CountryCurrencyView(ctk.CTkFrame):
    TITLE = "Country / Currency Settings"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = CountryCurrencyService(database, session)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))
        card = ctk.CTkScrollableFrame(self, height=360); card.pack(fill="both", expand=True, padx=16, pady=8)
        self._e = {}
        for k in _F:
            row = ctk.CTkFrame(card, fg_color="transparent"); row.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(row, text=k.replace("_", " ").title(), width=170, anchor="w").pack(side="left")
            e = ctk.CTkEntry(row, width=240); e.pack(side="left"); self._e[k] = e
        b = ctk.CTkFrame(self, fg_color="transparent"); b.pack(anchor="w", padx=16, pady=8)
        ctk.CTkButton(b, text="Reload", width=90, command=self._load).pack(side="left", padx=(0, 8))
        ctk.CTkButton(b, text="Save", width=90, command=self._save).pack(side="left")
        self.status = ctk.CTkLabel(self, text="", wraplength=520); self.status.pack(anchor="w", padx=16)
        self._load()

    def _load(self):
        data = self.service.load()
        for k, e in self._e.items():
            e.delete(0, "end"); e.insert(0, str(data.get(k, "")))
        if not self.service.available():
            self.status.configure(text="Note: country_currency_config table absent — showing defaults (read-only).", text_color=("gray40", "gray70"))

    def _save(self):
        try:
            msg = self.service.save({k: e.get() for k, e in self._e.items()})
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.status.configure(text=msg, text_color="#1E8449")
