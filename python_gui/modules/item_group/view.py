"""Item Group window."""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import ItemGroupRepo
from .service import ItemGroupError, ItemGroupForm, ItemGroupService


class ItemGroupView(ctk.CTkFrame):
    TITLE = "Item Group"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = ItemGroupService(ItemGroupRepo(database), session)
        self._editing: str | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.search_var = ctk.StringVar()
        e = ctk.CTkEntry(head, width=200, placeholder_text="Search…", textvariable=self.search_var)
        e.pack(side="right"); e.bind("<Return>", lambda _ev: self._reload())
        ctk.CTkButton(head, text="Search", width=70, command=self._reload).pack(side="right", padx=6)

        self.grid_widget = DataGrid(self, columns=[("code", "Code", 90), ("name", "Name", 200),
                                    ("itype", "Type", 60), ("orn", "Orn", 50)],
                                    on_select=self._on_select, key_field="code")
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)

        form = ctk.CTkScrollableFrame(self, width=300, label_text="Group")
        form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)
        self.code = self._field(form, "Code")
        self.name = self._field(form, "Name")
        self.mname = self._field(form, "Regional Name")
        ctk.CTkLabel(form, text="Type (G/S/P/O)").pack(anchor="w", padx=10)
        self.itype = ctk.CTkOptionMenu(form, width=120, values=["G", "S", "P", "O"]); self.itype.pack(anchor="w", padx=10, pady=(0, 6))
        self.pos = self._field(form, "Position")
        self.orn = ctk.BooleanVar(); ctk.CTkCheckBox(form, text="Ornament", variable=self.orn).pack(anchor="w", padx=10, pady=2)
        self.show = ctk.BooleanVar(); ctk.CTkCheckBox(form, text="Show in stock report", variable=self.show).pack(anchor="w", padx=10, pady=2)
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.pack(anchor="w", padx=10, pady=10)
        ctk.CTkButton(bt, text="New", width=60, command=self._new).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bt, text="Save", width=60, command=self._save).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bt, text="Delete", width=60, fg_color="#B03A2E", hover_color="#943126", command=self._delete).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=270); self.status.pack(anchor="w", padx=10)
        self._reload()

    def _field(self, parent, label):
        ctk.CTkLabel(parent, text=label).pack(anchor="w", padx=10, pady=(6, 0))
        e = ctk.CTkEntry(parent, width=260); e.pack(anchor="w", padx=10, pady=(0, 4)); return e

    def _reload(self):
        try:
            self.grid_widget.set_rows(self.service.list(self.search_var.get()))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        code = str(row.get("code", "")).strip()
        full = self.service.get(code) or row
        self._editing = code
        self._set(self.code, code); self.code.configure(state="disabled")
        self._set(self.name, full.get("name")); self._set(self.mname, full.get("mname"))
        self.itype.set(str(full.get("itype") or "G")); self._set(self.pos, full.get("pos") or 0)
        self.orn.set(str(full.get("orn") or "N").upper() == "Y")
        self.show.set(str(full.get("showinstkrep") or "N").upper() == "Y")
        self.status.configure(text=f"Editing {code}", text_color=("gray30", "gray70"))

    @staticmethod
    def _set(e, v):
        e.configure(state="normal"); e.delete(0, "end"); e.insert(0, str(v if v is not None else ""))

    def _new(self):
        self._editing = None
        for e in (self.code, self.name, self.mname): self._set(e, "")
        self._set(self.pos, "0"); self.itype.set("G"); self.orn.set(False); self.show.set(False)
        self.grid_widget.clear_selection()
        self.status.configure(text="New group", text_color=("gray30", "gray70"))

    def _form(self):
        return ItemGroupForm(code=self.code.get(), name=self.name.get(), mname=self.mname.get(),
                             type=self.itype.get(), ornament=self.orn.get(), position=self.pos.get() or 0,
                             show_in_stock=self.show.get())

    def _save(self):
        try:
            msg = self.service.save(self._form(), "E" if self._editing else "A")
        except ItemGroupError as exc:
            self.status.configure(text=str(exc), text_color="#C0392B"); return
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.grid_widget.select_key(self.code.get().strip().upper())
        self.status.configure(text=msg, text_color="#1E8449")

    def _delete(self):
        code = (self.code.get() or "").strip().upper()
        if not code or not messagebox.askyesno("Delete", f"Delete group '{code}'?"):
            return
        try:
            msg = self.service.delete(code)
        except ItemGroupError as exc:
            messagebox.showwarning("Cannot delete", str(exc)); return
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._new(); self._reload(); self.status.configure(text=msg, text_color="#1E8449")
