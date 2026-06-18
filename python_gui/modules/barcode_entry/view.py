"""Barcode Single Entry window."""

from __future__ import annotations

from datetime import date
from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import BarcodeRepo
from .service import BarcodeError, BarcodeService

_FIELDS = [("bcode", "Barcode #"), ("icode", "Item Code"), ("qty", "Qty"),
           ("weight", "Weight"), ("qtype", "Purity"), ("wastage", "Wastage"),
           ("mc", "MC"), ("mcrate", "MC Rate"), ("rate", "Rate"), ("docno", "Doc No"),
           ("smithcode", "Smith"), ("counter", "Counter")]


class BarcodeEntryView(ctk.CTkFrame):
    TITLE = "Barcode Single Entry"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = BarcodeService(BarcodeRepo(database), session)
        self._editing = False
        self._e: dict[str, ctk.CTkEntry] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.search_var = ctk.StringVar()
        e = ctk.CTkEntry(head, width=180, placeholder_text="Search…", textvariable=self.search_var)
        e.pack(side="right"); e.bind("<Return>", lambda _ev: self._reload())
        ctk.CTkButton(head, text="Search", width=70, command=self._reload).pack(side="right", padx=6)

        self.grid_widget = DataGrid(self, columns=[("bcode", "Barcode", 90), ("icode", "Item", 90),
                                    ("qty", "Qty", 60), ("weight", "Weight", 80), ("qtype", "Purity", 70),
                                    ("stk", "Stk", 50)], on_select=self._on_select, key_field="bcode")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)

        form = ctk.CTkScrollableFrame(self, width=300, label_text="Barcode"); form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        ctk.CTkLabel(form, text="Date").pack(anchor="w", padx=10, pady=(6, 0))
        self.tdate = ctk.CTkEntry(form, width=140); self.tdate.pack(anchor="w", padx=10); self.tdate.insert(0, date.today().isoformat())
        for key, label in _FIELDS:
            ctk.CTkLabel(form, text=label).pack(anchor="w", padx=10, pady=(4, 0))
            ent = ctk.CTkEntry(form, width=200); ent.pack(anchor="w", padx=10); self._e[key] = ent
        self.sold = ctk.BooleanVar(); ctk.CTkCheckBox(form, text="Sold (stk=N)", variable=self.sold).pack(anchor="w", padx=10, pady=4)
        ctk.CTkButton(form, text="Load Item", width=100, command=self._load_item).pack(anchor="w", padx=10, pady=2)
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.pack(anchor="w", padx=10, pady=8)
        ctk.CTkButton(bt, text="New", width=58, command=self._new).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Save", width=58, command=self._save).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bt, text="Delete", width=58, fg_color="#B03A2E", hover_color="#943126", command=self._delete).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=270); self.status.pack(anchor="w", padx=10)
        self._new(); self._reload()

    def _reload(self):
        try:
            self.grid_widget.set_rows(self.service.search(self.search_var.get()))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        b = self.service.get(int(row["bcode"])) or row
        self._editing = True
        for key, ent in self._e.items():
            self._set(ent, b.get(key))
        self._e["bcode"].configure(state="disabled")
        self.sold.set(str(b.get("stk") or "Y").upper() == "N")
        self.status.configure(text=f"Editing {row['bcode']}", text_color=("gray30", "gray70"))

    @staticmethod
    def _set(e, v):
        e.configure(state="normal"); e.delete(0, "end"); e.insert(0, str(v if v is not None else ""))

    def _new(self):
        self._editing = False
        for ent in self._e.values():
            self._set(ent, "")
        try:
            self._set(self._e["bcode"], self.service.next_barcode())
        except Exception:
            pass
        self.sold.set(False)
        self.grid_widget.clear_selection()
        self.status.configure(text="New barcode", text_color=("gray30", "gray70"))

    def _load_item(self):
        item = self.service.load_item(self._e["icode"].get())
        if not item:
            self.status.configure(text="Item not found", text_color="#C0392B"); return
        self._set(self._e["wastage"], item.get("wastage"))
        self._set(self._e["mcrate"], item.get("mcharge"))
        self._set(self._e["qtype"], item.get("defquality"))
        self.status.configure(text=f"Loaded {item.get('name')}", text_color=("gray30", "gray70"))

    def _form(self):
        d = {k: e.get() for k, e in self._e.items()}
        d["tdate"] = self.tdate.get()
        d["sold"] = "Y" if self.sold.get() else "N"
        return d

    def _save(self):
        try:
            res = self.service.save(self._form(), "edit" if self._editing else "add")
        except (BarcodeError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.status.configure(text=res["message"], text_color="#1E8449")

    def _delete(self):
        try:
            bcode = int(self._e["bcode"].get())
        except ValueError:
            self.status.configure(text="Invalid barcode", text_color="#C0392B"); return
        if not messagebox.askyesno("Delete", f"Delete barcode {bcode}?"):
            return
        try:
            msg = self.service.delete(bcode)
        except BarcodeError as exc:
            messagebox.showwarning("Cannot delete", str(exc)); return
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._new(); self._reload(); self.status.configure(text=msg, text_color="#1E8449")
