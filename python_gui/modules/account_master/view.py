"""Account Master window (customtkinter).

Equivalent of the Account Master page (AccountMasterController::account). List of
accounts + a form with account type (R/E/A/L), cash/bank markers, opening
balance with debit/credit, group + BS-head pickers, and status flags.
"""

from __future__ import annotations

from decimal import Decimal
from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import AccountMasterRepo
from .service import AccountError, AccountForm, AccountMasterService

_TYPES = [("Asset", "A"), ("Liability", "L"), ("Revenue", "R"), ("Expense", "E")]


class AccountMasterView(ctk.CTkFrame):
    TITLE = "Account Master"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = AccountMasterService(AccountMasterRepo(database), session)
        self._editing: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        self.search_var = ctk.StringVar()
        e = ctk.CTkEntry(head, width=220, placeholder_text="Search…", textvariable=self.search_var)
        e.pack(side="right")
        e.bind("<Return>", lambda _ev: self._reload())
        ctk.CTkButton(head, text="Search", width=70, command=self._reload).pack(side="right", padx=6)

        self.grid_widget = DataGrid(
            self,
            columns=[("accode", "Code", 100), ("name", "Name", 220),
                     ("grcode", "Group", 90), ("actype1", "Type", 60)],
            on_select=self._on_select, key_field="accode",
        )
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=6)

        self._build_form()
        self._reload()

    # -- form ---------------------------------------------------------------
    def _build_form(self) -> None:
        form = ctk.CTkScrollableFrame(self, width=360, label_text="Account")
        form.grid(row=2, column=1, sticky="ns", padx=(6, 12), pady=6)
        r = 0

        def field(label, width=300):
            nonlocal r
            ctk.CTkLabel(form, text=label).grid(row=r, column=0, sticky="w", padx=10, pady=(6, 0))
            ent = ctk.CTkEntry(form, width=width)
            ent.grid(row=r + 1, column=0, columnspan=2, sticky="w", padx=10)
            r += 2
            return ent

        self.code_entry = field("Account Code")
        self.desc_entry = field("Description")

        ctk.CTkLabel(form, text="Group").grid(row=r, column=0, sticky="w", padx=10, pady=(6, 0))
        self.grp_menu = ctk.CTkOptionMenu(form, width=300, values=["—"])
        self.grp_menu.grid(row=r + 1, column=0, columnspan=2, sticky="w", padx=10)
        r += 2

        ctk.CTkLabel(form, text="BS Head (Asset/Liability)").grid(row=r, column=0, sticky="w", padx=10, pady=(6, 0))
        self.bs_menu = ctk.CTkOptionMenu(form, width=300, values=["—"])
        self.bs_menu.grid(row=r + 1, column=0, columnspan=2, sticky="w", padx=10)
        r += 2

        ctk.CTkLabel(form, text="Account Type").grid(row=r, column=0, sticky="w", padx=10, pady=(6, 0))
        self.type_var = ctk.StringVar(value="A")
        tf = ctk.CTkFrame(form, fg_color="transparent")
        tf.grid(row=r + 1, column=0, columnspan=2, sticky="w", padx=8)
        for label, code in _TYPES:
            ctk.CTkRadioButton(tf, text=label, variable=self.type_var, value=code).pack(side="left", padx=4)
        r += 2

        self.cash_var = ctk.BooleanVar(value=False)
        self.bank_var = ctk.BooleanVar(value=False)
        cb = ctk.CTkFrame(form, fg_color="transparent")
        cb.grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ctk.CTkCheckBox(cb, text="Cash (H)", variable=self.cash_var).pack(side="left", padx=4)
        ctk.CTkCheckBox(cb, text="Bank (B)", variable=self.bank_var).pack(side="left", padx=4)
        r += 1

        ctk.CTkLabel(form, text="Opening Balance").grid(row=r, column=0, sticky="w", padx=10, pady=(6, 0))
        self.bal_entry = ctk.CTkEntry(form, width=180)
        self.bal_entry.grid(row=r + 1, column=0, sticky="w", padx=10)
        self.bal_type = ctk.CTkOptionMenu(form, width=100, values=["debit", "credit"])
        self.bal_type.grid(row=r + 1, column=1, sticky="w")
        r += 2

        self.note_entry = field("Note")

        self.flags = {}
        ff = ctk.CTkFrame(form, fg_color="transparent")
        ff.grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        for key, label, default in [("display", "Display", True), ("reserve", "Reserved", False),
                                    ("removed", "Removed", False), ("blocked", "Blocked", False)]:
            v = ctk.BooleanVar(value=default)
            ctk.CTkCheckBox(ff, text=label, variable=v).pack(side="left", padx=4)
            self.flags[key] = v
        r += 1

        btns = ctk.CTkFrame(form, fg_color="transparent")
        btns.grid(row=r, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 8))
        ctk.CTkButton(btns, text="New", width=64, command=self._new).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Save", width=64, command=self._save).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Delete", width=64, fg_color="#B03A2E",
                      hover_color="#943126", command=self._delete).pack(side="left")
        r += 1
        self.status = ctk.CTkLabel(form, text="", wraplength=320)
        self.status.grid(row=r, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

        self._load_pickers()

    def _load_pickers(self) -> None:
        try:
            groups = self.service.list_groups()
            self.grp_menu.configure(values=[g["grcode"] for g in groups] or ["—"])
            heads = self.service.list_bs_heads()
            self.bs_menu.configure(values=["—"] + [h["hcode"] for h in heads])
        except Exception as exc:
            self._error(str(exc).splitlines()[0])

    # -- data flow ----------------------------------------------------------
    def _reload(self) -> None:
        try:
            self.grid_widget.set_rows(self.service.list(self.search_var.get()))
        except Exception as exc:
            self._error(str(exc).splitlines()[0])

    def _on_select(self, row: dict) -> None:
        code = str(row.get("accode", "")).strip()
        data = self.service.load(code)
        if not data:
            return
        self._editing = code
        self._set(self.code_entry, data["accode"])
        self.code_entry.configure(state="disabled")
        self._set(self.desc_entry, data["desc"])
        self.grp_menu.set(data["grcode"] or "—")
        self.bs_menu.set(data["bshead"] or "—")
        self.type_var.set("R" if data["revenue_checked"] else "E" if data["expense_checked"]
                          else "L" if data["liability_checked"] else "A")
        self.cash_var.set(data["cash_checked"])
        self.bank_var.set(data["bank_checked"])
        self._set(self.bal_entry, str(Decimal(str(data["balance"]))))
        self.bal_type.set("debit" if data["debit_checked"] else "credit")
        self._set(self.note_entry, data["note"])
        self.flags["display"].set(data["display_checked"])
        self.flags["reserve"].set(data["reserve_checked"])
        self.flags["removed"].set(data["removed_checked"])
        self.flags["blocked"].set(data["blocked_checked"])
        self.status.configure(text=f"Editing {code}", text_color=("gray30", "gray70"))

    @staticmethod
    def _set(entry, value) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, str(value or ""))

    def _new(self) -> None:
        self._editing = None
        for e in (self.code_entry, self.desc_entry, self.note_entry):
            self._set(e, "")
        self._set(self.bal_entry, "0")
        self.bal_type.set("debit")
        self.type_var.set("A")
        self.cash_var.set(False)
        self.bank_var.set(False)
        self.flags["display"].set(True)
        for k in ("reserve", "removed", "blocked"):
            self.flags[k].set(False)
        self.grid_widget.clear_selection()
        self.status.configure(text="New account", text_color=("gray30", "gray70"))

    def _form(self) -> AccountForm:
        actype2 = "H" if self.cash_var.get() else "B" if self.bank_var.get() else ""
        data = {
            "mode": "E" if self._editing else "A",
            "accode": self.code_entry.get(),
            "original_accode": self._editing or self.code_entry.get(),
            "desc": self.desc_entry.get(),
            "grcode": "" if self.grp_menu.get() == "—" else self.grp_menu.get(),
            "bshead": "" if self.bs_menu.get() == "—" else self.bs_menu.get(),
            "actype1": self.type_var.get(),
            "actype2": actype2,
            "balance": self.bal_entry.get() or "0",
            "balance_type": self.bal_type.get(),
            "note": self.note_entry.get(),
        }
        for key, var in self.flags.items():
            if var.get():
                data[key] = "1"
        return AccountForm(data)

    def _save(self) -> None:
        try:
            msg = self.service.save(self._form())
        except AccountError as exc:
            self._error(str(exc))
            return
        except Exception as exc:
            self._error(str(exc).splitlines()[0])
            return
        code = self.code_entry.get().strip().upper()
        self._reload()
        self.grid_widget.select_key(code)
        self.status.configure(text=msg, text_color="#1E8449")

    def _delete(self) -> None:
        code = (self.code_entry.get() or "").strip().upper()
        if not code:
            self._error("Select an account to delete")
            return
        if not messagebox.askyesno("Delete", f"Delete account '{code}'?"):
            return
        try:
            msg = self.service.delete(code)
        except AccountError as exc:
            messagebox.showwarning("Cannot delete", str(exc))
            return
        except Exception as exc:
            self._error(str(exc).splitlines()[0])
            return
        self._new()
        self._reload()
        self.status.configure(text=msg, text_color="#1E8449")

    def _error(self, msg: str) -> None:
        self.status.configure(text=msg, text_color="#C0392B")
