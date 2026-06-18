"""Model Master window (bulk names by type)."""
from __future__ import annotations
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from .service import ModelError, ModelMasterService


class ModelMasterView(ctk.CTkFrame):
    TITLE = "Model Master"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = ModelMasterService(database, session)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))
        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(bar, text="Type").pack(side="left", padx=(0, 6))
        self.mtype = ctk.CTkOptionMenu(bar, width=120, values=["M", "S"], command=lambda _v: self._load())
        self.mtype.pack(side="left")
        ctk.CTkLabel(self, text="One model name per line:").pack(anchor="w", padx=16, pady=(8, 0))
        self.text = ctk.CTkTextbox(self, height=320); self.text.pack(fill="both", expand=True, padx=16, pady=6)
        b = ctk.CTkFrame(self, fg_color="transparent"); b.pack(fill="x", padx=16, pady=6)
        ctk.CTkButton(b, text="Reload", width=90, command=self._load).pack(side="left", padx=(0, 8))
        ctk.CTkButton(b, text="Save", width=90, command=self._save).pack(side="left")
        self.status = ctk.CTkLabel(self, text=""); self.status.pack(anchor="w", padx=16)
        self._load()

    def _load(self):
        try:
            names = [r["name"] for r in self.service.list(self.mtype.get())]
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self.text.delete("1.0", "end"); self.text.insert("1.0", "\n".join(names))

    def _save(self):
        names = [n for n in self.text.get("1.0", "end").splitlines()]
        try:
            self.service.save(self.mtype.get(), names)
        except (ModelError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._load(); self.status.configure(text="Saved.", text_color="#1E8449")
