"""Item Master window — common item fields (full payload is column-filtered)."""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import ItemMasterRepo
from .service import ItemMasterError, ItemMasterService

# form_key -> label for the text/number fields exposed in the desktop form
_TEXT = [
    ("code", "Code *"), ("desc", "Description *"), ("regional", "Regional Name"),
    ("wastage", "Wastage"), ("mcrate", "MC Rate"), ("vaperc", "VA %"),
    ("touch", "Touch"), ("rate", "Rate"), ("stktouch", "Stock Touch"),
]
_BOOL = [("ornament", "Ornament"), ("taxable", "Taxable"), ("reserve", "Reserved"),
         ("disable", "Disabled"), ("bccompulsory", "BC Compulsory")]


class ItemMasterView(ctk.CTkFrame):
    TITLE = "Item Master"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = ItemMasterService(ItemMasterRepo(database), session)
        self._editing = False
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._bools: dict[str, ctk.BooleanVar] = {}
        try:
            self._opts = self.service.options()
        except Exception:
            self._opts = {"groups": [], "subgroups": [], "stocktypes": [], "qualities": [], "billtypes": []}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.search_var = ctk.StringVar()
        e = ctk.CTkEntry(head, width=200, placeholder_text="Search…", textvariable=self.search_var)
        e.pack(side="right"); e.bind("<Return>", lambda _ev: self._reload())
        ctk.CTkButton(head, text="Search", width=70, command=self._reload).pack(side="right", padx=6)

        self.grid_widget = DataGrid(self, columns=[("code", "Code", 90), ("name", "Name", 200),
                                    ("itype", "Type", 60), ("grpcode", "Group", 80)],
                                    on_select=self._on_select, key_field="code")
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)

        form = ctk.CTkScrollableFrame(self, width=320, label_text="Item")
        form.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)
        for key, label in _TEXT:
            ctk.CTkLabel(form, text=label).pack(anchor="w", padx=10, pady=(4, 0))
            ent = ctk.CTkEntry(form, width=260); ent.pack(anchor="w", padx=10)
            self._entries[key] = ent
        self._menu(form, "itype", "Item Type", ["G", "S", "P", "D", "O"])
        self._menu(form, "grpcode", "Group", [g["code"] for g in self._opts["groups"]])
        self._menu(form, "subgrpcode", "Sub-Group", [g["code"] for g in self._opts["subgroups"]])
        self._menu(form, "stktype", "Stock Type", [g["code"] for g in self._opts["stocktypes"]])
        self._menu(form, "qtype", "Purity", [str(g["code"]) for g in self._opts["qualities"]])
        for key, label in _BOOL:
            v = ctk.BooleanVar(); ctk.CTkCheckBox(form, text=label, variable=v).pack(anchor="w", padx=10, pady=1)
            self._bools[key] = v
        bt = ctk.CTkFrame(form, fg_color="transparent"); bt.pack(anchor="w", padx=10, pady=8)
        ctk.CTkButton(bt, text="New", width=60, command=self._new).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bt, text="Save", width=60, command=self._save).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bt, text="Delete", width=60, fg_color="#B03A2E", hover_color="#943126", command=self._delete).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=290); self.status.pack(anchor="w", padx=10)
        self._menus = getattr(self, "_menus", {})
        self._new(); self._reload()

    def _menu(self, parent, key, label, values):
        ctk.CTkLabel(parent, text=label).pack(anchor="w", padx=10, pady=(4, 0))
        m = ctk.CTkOptionMenu(parent, width=200, values=(["—"] + values) if values else ["—"])
        m.pack(anchor="w", padx=10)
        if not hasattr(self, "_menus"):
            self._menus = {}
        self._menus[key] = m

    def _reload(self):
        try:
            self.grid_widget.set_rows(self.service.search(self.search_var.get()))
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B")

    def _on_select(self, row):
        code = str(row.get("code", "")).strip()
        item = self.service.get(code) or row
        self._editing = True
        for key, ent in self._entries.items():
            src = "name" if key == "desc" else "regionalname" if key == "regional" \
                else "mcharge" if key == "mcrate" else key
            self._set(ent, item.get(src))
        self._entries["code"].configure(state="disabled")
        self._menus["itype"].set(str(item.get("itype") or "G"))
        self._menus["grpcode"].set(str(item.get("grpcode") or "—").strip() or "—")
        self._menus["subgrpcode"].set(str(item.get("subgrpcode") or "—").strip() or "—")
        self._menus["stktype"].set(str(item.get("defstktype") or "—").strip() or "—")
        self._menus["qtype"].set(str(item.get("qtype") or item.get("defquality") or "—").strip() or "—")
        self._bools["ornament"].set(str(item.get("ornament") or "").upper() == "Y")
        self._bools["taxable"].set(str(item.get("taxable") or "").upper() == "Y")
        self._bools["reserve"].set(str(item.get("reserve") or "").upper() == "Y")
        self._bools["disable"].set(int(item.get("disabled") or 0) == 1)
        self._bools["bccompulsory"].set(str(item.get("bccompulsory") or "").upper() == "Y")
        self.status.configure(text=f"Editing {code}", text_color=("gray30", "gray70"))

    @staticmethod
    def _set(e, v):
        e.configure(state="normal"); e.delete(0, "end"); e.insert(0, str(v if v is not None else ""))

    def _new(self):
        self._editing = False
        for ent in self._entries.values():
            self._set(ent, "")
        for m in self._menus.values():
            m.set("—")
        self._menus["itype"].set("G")
        for v in self._bools.values():
            v.set(False)
        self.grid_widget.clear_selection()
        self.status.configure(text="New item", text_color=("gray30", "gray70"))

    def _form(self):
        f = {k: e.get() for k, e in self._entries.items()}
        for key, m in self._menus.items():
            val = m.get()
            f[key] = "" if val == "—" else val
        for key, v in self._bools.items():
            f[key] = v.get()
        return f

    def _save(self):
        try:
            msg = self.service.save(self._form(), "edit" if self._editing else "add",
                                    code_locked=self._editing)
        except ItemMasterError as exc:
            self.status.configure(text=str(exc), text_color="#C0392B"); return
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._reload(); self.grid_widget.select_key(self._entries["code"].get().strip().upper())
        self.status.configure(text=msg, text_color="#1E8449")

    def _delete(self):
        code = (self._entries["code"].get() or "").strip().upper()
        if not code or not messagebox.askyesno("Delete", f"Delete item '{code}'?"):
            return
        try:
            msg = self.service.delete(code)
        except ItemMasterError as exc:
            messagebox.showwarning("Cannot delete", str(exc)); return
        except Exception as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        self._new(); self._reload(); self.status.configure(text=msg, text_color="#1E8449")
