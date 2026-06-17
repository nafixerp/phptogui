"""Parties window (customtkinter) — Customer / Supplier / Staff / etc.

Equivalent of resources/views/native/customer/form.blade.php + list. A party
type selector switches ctype (C/S/F/D/G/R/J); the list filters by type with
search; the form covers the common clients fields. Full save/accountm posting
goes through PartiesService. (Goldsmith weight tab, photo, CSV: deferred.)
"""

from __future__ import annotations

from decimal import Decimal
from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import PartiesRepo
from .service import VALID_TYPES, PartiesService, PartyError, PartyForm

# (field key, label) for the simple text inputs
_TEXT_FIELDS = [
    ("name", "Name *"), ("addr1", "Address 1"), ("addr2", "Address 2"),
    ("addr3", "Address 3"), ("city", "City"), ("telephone", "Telephone"),
    ("mobile", "Mobile"), ("email", "Email"), ("state", "State"),
    ("grp", "Group"), ("idno", "ID No"),
]


class PartiesView(ctk.CTkFrame):
    TITLE = "Parties"

    def __init__(self, master, database: Database, session: AppSession, ctype: str = "C"):
        super().__init__(master, fg_color="transparent")
        self.service = PartiesService(PartiesRepo(database), session)
        self.ctype = self.service.normalize_type(ctype)
        self._editing_code: str | None = None
        self._entries: dict[str, ctk.CTkEntry] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_list()
        self._build_form()
        self._reload()

    # -- header / type selector --------------------------------------------
    def _build_header(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))

        ctk.CTkLabel(head, text="Party", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.type_var = ctk.StringVar(value=self.ctype)
        ctk.CTkOptionMenu(
            head, width=140, variable=self.type_var, values=list(VALID_TYPES),
            command=self._change_type,
        ).pack(side="left", padx=12)
        self.type_label = ctk.CTkLabel(head, text=self.service.type_title(self.ctype))
        self.type_label.pack(side="left")

        self.search_var = ctk.StringVar()
        ent = ctk.CTkEntry(head, width=220, placeholder_text="Search…", textvariable=self.search_var)
        ent.pack(side="right")
        ent.bind("<Return>", lambda _e: self._reload())
        ctk.CTkButton(head, text="Search", width=70, command=self._reload).pack(side="right", padx=6)

    def _build_list(self) -> None:
        self.grid_widget = DataGrid(
            self,
            columns=[("code", "Code", 90), ("name", "Name", 200),
                     ("mobile", "Mobile", 110), ("city", "City", 110)],
            on_select=self._on_select, key_field="code",
        )
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)

    # -- form ---------------------------------------------------------------
    def _build_form(self) -> None:
        form = ctk.CTkScrollableFrame(self, width=340, label_text="Details")
        form.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)

        row = 0
        ctk.CTkLabel(form, text="Code").grid(row=row, column=0, sticky="w", padx=10, pady=(8, 0))
        self.code_entry = ctk.CTkEntry(form, width=160, placeholder_text="(auto)")
        self.code_entry.grid(row=row + 1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))
        row += 2

        for key, label in _TEXT_FIELDS:
            ctk.CTkLabel(form, text=label).grid(row=row, column=0, sticky="w", padx=10)
            e = ctk.CTkEntry(form, width=300)
            e.grid(row=row + 1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))
            self._entries[key] = e
            row += 2

        # Opening balance + dr/cr
        ctk.CTkLabel(form, text="Opening Balance").grid(row=row, column=0, sticky="w", padx=10)
        self.opbal_entry = ctk.CTkEntry(form, width=180)
        self.opbal_entry.grid(row=row + 1, column=0, sticky="w", padx=10, pady=(0, 6))
        self.opbal_type = ctk.CTkOptionMenu(form, width=100, values=["debit", "credit"])
        self.opbal_type.grid(row=row + 1, column=1, sticky="w", pady=(0, 6))
        row += 2

        ctk.CTkLabel(form, text="Opening Weight").grid(row=row, column=0, sticky="w", padx=10)
        self.opwgt_entry = ctk.CTkEntry(form, width=180)
        self.opwgt_entry.grid(row=row + 1, column=0, sticky="w", padx=10, pady=(0, 6))
        self.opwgt_type = ctk.CTkOptionMenu(form, width=100, values=["debit", "credit"])
        self.opwgt_type.grid(row=row + 1, column=1, sticky="w", pady=(0, 6))
        row += 2

        self.removed_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(form, text="Removed", variable=self.removed_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4)
        row += 1

        btns = ctk.CTkFrame(form, fg_color="transparent")
        btns.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 8))
        ctk.CTkButton(btns, text="New", width=64, command=self._new).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Save", width=64, command=self._save).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Delete", width=64, fg_color="#B03A2E",
                      hover_color="#943126", command=self._delete).pack(side="left")
        row += 1

        self.status = ctk.CTkLabel(form, text="", wraplength=300)
        self.status.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

    # -- data flow ----------------------------------------------------------
    def _reload(self) -> None:
        try:
            rows = self.service.list(self.ctype, self.search_var.get())
            self.grid_widget.set_rows(rows)
        except Exception as exc:
            self._error(str(exc).splitlines()[0])

    def _change_type(self, value: str) -> None:
        self.ctype = self.service.normalize_type(value)
        self.type_label.configure(text=self.service.type_title(self.ctype))
        self._new()
        self._reload()

    def _on_select(self, row: dict) -> None:
        code = str(row.get("code", "")).strip()
        full = self.service.get(code) or row
        self._editing_code = code
        self.code_entry.delete(0, "end")
        self.code_entry.insert(0, code)
        self.code_entry.configure(state="disabled")
        for key, e in self._entries.items():
            e.delete(0, "end")
            e.insert(0, str(full.get(key) or "").strip())
        self._set_signed(self.opbal_entry, self.opbal_type, full.get("opbalance"))
        self._set_signed(self.opwgt_entry, self.opwgt_type, full.get("opweight"))
        self.removed_var.set(int(full.get("removed") or 0) == 1)
        self.status.configure(text=f"Editing {code}", text_color=("gray30", "gray70"))

    @staticmethod
    def _set_signed(entry, type_menu, value) -> None:
        d = Decimal(str(value or 0))
        entry.delete(0, "end")
        entry.insert(0, str(d.copy_abs()))
        type_menu.set("credit" if d > 0 else "debit")  # credit=+, debit=-

    def _new(self) -> None:
        self._editing_code = None
        self.code_entry.configure(state="normal")
        self.code_entry.delete(0, "end")
        for e in self._entries.values():
            e.delete(0, "end")
        for ent, menu in ((self.opbal_entry, self.opbal_type), (self.opwgt_entry, self.opwgt_type)):
            ent.delete(0, "end")
            ent.insert(0, "0")
            menu.set("debit")
        self.removed_var.set(False)
        self.grid_widget.clear_selection()
        self._suggest_code()
        self.status.configure(text=f"New {self.service.type_title(self.ctype)}",
                              text_color=("gray30", "gray70"))

    def _suggest_code(self) -> None:
        try:
            self.code_entry.delete(0, "end")
            self.code_entry.insert(0, self.service.next_code(self.ctype))
        except Exception:
            pass  # suggestion is best-effort

    def _build_form_payload(self) -> PartyForm:
        data = {key: e.get() for key, e in self._entries.items()}
        data.update({
            "type": self.ctype,
            "code": self.code_entry.get(),
            "original_code": self._editing_code or "",
            "opbalance": self.opbal_entry.get() or "0",
            "balance_type": self.opbal_type.get(),
            "opweight": self.opwgt_entry.get() or "0",
            "weight_type": self.opwgt_type.get(),
        })
        if self.removed_var.get():
            data["removed"] = "1"
        return PartyForm(data)

    def _save(self) -> None:
        try:
            saved = self.service.save(self._build_form_payload())
        except PartyError as exc:
            self._error(str(exc))
            return
        except Exception as exc:
            self._error(str(exc).splitlines()[0])
            return
        code = str(saved.get("code", ""))
        self._reload()
        self.grid_widget.select_key(code)
        self.status.configure(text=f"Saved {code}", text_color="#1E8449")

    def _delete(self) -> None:
        code = (self.code_entry.get() or "").strip()
        if not code:
            self._error("Select a record to delete")
            return
        if not messagebox.askyesno("Delete", f"Delete '{code}'?"):
            return
        try:
            self.service.delete(code)
        except PartyError as exc:
            messagebox.showwarning("Cannot delete", str(exc))
            return
        except Exception as exc:
            self._error(str(exc).splitlines()[0])
            return
        self._new()
        self._reload()
        self.status.configure(text=f"Deleted {code}", text_color="#1E8449")

    def _error(self, msg: str) -> None:
        self.status.configure(text=msg, text_color="#C0392B")


# Thin subclasses so the sidebar can open a specific party type directly.
class CustomerView(PartiesView):
    def __init__(self, master, database, session):
        super().__init__(master, database, session, ctype="C")


class SupplierView(PartiesView):
    def __init__(self, master, database, session):
        super().__init__(master, database, session, ctype="S")
