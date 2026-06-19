"""Purity Testing window."""
from __future__ import annotations
from datetime import date
import customtkinter as ctk
from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .service import PurityTestingError, PurityTestingService


class PurityTestingView(ctk.CTkFrame):
    TITLE = "Purity Testing"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PurityTestingService(database, control=getattr(session, "gilevel", 1))
        self._edit = 0
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent"); head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        try:
            ctk.CTkLabel(head, text=f"Next Doc: {self.service.next_doc_no()}").pack(side="left", padx=16)
        except Exception:
            pass
        ctk.CTkButton(head, text="Save", width=90, command=self._save).pack(side="right", padx=6)
        entry = ctk.CTkFrame(self, fg_color="transparent"); entry.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        self.inputs: dict[str, ctk.CTkEntry] = {}
        for key, label in [("docno", "Doc No"), ("customer", "Customer"), ("rcvdwgt", "Rcvd Wt"),
                           ("purityinperc", "Purity %"), ("purityinct", "Purity ct"), ("typeofsample", "Sample")]:
            ctk.CTkLabel(entry, text=label).pack(side="left", padx=(6, 2))
            e = ctk.CTkEntry(entry, width=90); e.pack(side="left"); self.inputs[key] = e
        self.grid_widget = DataGrid(self, columns=[("slno", "Slno", 70), ("docno", "Doc", 80), ("tdate", "Date", 100),
                                    ("customer", "Customer", 180), ("purityinperc", "Purity %", 90), ("rcvdwgt", "Rcvd Wt", 90)],
                                    on_select=self._on_select, key_field="slno")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(row=3, column=0, sticky="ew", padx=14, pady=4)
        self._reload()

    def _reload(self):
        try:
            rows = self.service.list()
            self.grid_widget.set_rows([{"slno": r.get("slno"), "docno": str(r.get("docno") or ""), "tdate": str(r.get("tdate") or ""),
                                        "customer": str(r.get("customer") or ""), "purityinperc": str(r.get("purityinperc") or ""),
                                        "rcvdwgt": str(r.get("rcvdwgt") or "")} for r in rows])
            self.status.configure(text=f"{len(rows)} record(s).", text_color=("gray20", "gray80"))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        self._edit = row.get("slno") or 0
        for k, e in self.inputs.items():
            e.delete(0, "end"); e.insert(0, str(row.get(k) or ""))

    def _save(self):
        data = {k: e.get() for k, e in self.inputs.items()}
        data["tdate"] = date.today().isoformat()
        try:
            res = self.service.save(data, edit_slno=self._edit)
        except (PurityTestingError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._edit = 0; self._reload()
        self.status.configure(text=f'{"Updated" if res["updated"] else "Saved"} slno {res["slno"]}', text_color="#1E8449")
