"""User Access window (customtkinter).

Equivalent of user-access.index: a user list, a form (code, name, password,
limits), and grouped permission checkboxes (from core.permissions). Saving
writes userm + userd through UserAccessService.
"""

from __future__ import annotations

from decimal import Decimal
from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ...core.permissions import GROUPED, label_for
from ..widgets.datagrid import DataGrid
from .repo import UserAccessRepo
from .service import UserAccessError, UserAccessForm, UserAccessService

_LIMITS = [
    ("maxcredit", "Max Credit"), ("maxdisc", "Max Discount"),
    ("maxdiscperc", "Max Disc %"), ("minvaperc", "Min VA %"),
    ("maxadjwgtbc", "Max Adj Wgt BC"),
]


class UserAccessView(ctk.CTkFrame):
    TITLE = "User Access"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = UserAccessService(UserAccessRepo(database), session)
        self._editing: str | None = None
        self._limit_entries: dict[str, ctk.CTkEntry] = {}
        self._perm_vars: dict[str, ctk.BooleanVar] = {}

        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 6))

        # users list
        self.grid_widget = DataGrid(
            self, columns=[("code", "Code", 90), ("name", "Name", 180)],
            on_select=self._on_select, key_field="code",
        )
        self.grid_widget.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)

        self._build_form()
        self._build_permissions()
        self._reload()

    # -- form ---------------------------------------------------------------
    def _build_form(self) -> None:
        form = ctk.CTkScrollableFrame(self, width=260, label_text="User")
        form.grid(row=1, column=1, sticky="ns", padx=6, pady=6)

        ctk.CTkLabel(form, text="Code").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 0))
        self.code_entry = ctk.CTkEntry(form, width=160)
        self.code_entry.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 6))

        ctk.CTkLabel(form, text="Name").grid(row=2, column=0, sticky="w", padx=10)
        self.name_entry = ctk.CTkEntry(form, width=220)
        self.name_entry.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 6))

        ctk.CTkLabel(form, text="Password (blank = keep)").grid(row=4, column=0, sticky="w", padx=10)
        self.pw_entry = ctk.CTkEntry(form, width=220, show="•")
        self.pw_entry.grid(row=5, column=0, sticky="w", padx=10, pady=(0, 6))

        r = 6
        for key, label in _LIMITS:
            ctk.CTkLabel(form, text=label).grid(row=r, column=0, sticky="w", padx=10)
            e = ctk.CTkEntry(form, width=140)
            e.grid(row=r + 1, column=0, sticky="w", padx=10, pady=(0, 4))
            self._limit_entries[key] = e
            r += 2

        btns = ctk.CTkFrame(form, fg_color="transparent")
        btns.grid(row=r, column=0, sticky="w", padx=10, pady=(10, 8))
        ctk.CTkButton(btns, text="New", width=58, command=self._new).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btns, text="Save", width=58, command=self._save).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btns, text="Delete", width=58, fg_color="#B03A2E",
                      hover_color="#943126", command=self._delete).pack(side="left")
        self.status = ctk.CTkLabel(form, text="", wraplength=230)
        self.status.grid(row=r + 1, column=0, sticky="w", padx=10, pady=(0, 10))

    def _build_permissions(self) -> None:
        panel = ctk.CTkScrollableFrame(self, label_text="Permissions (checked = blocked / flag set)")
        panel.grid(row=1, column=2, sticky="nsew", padx=(6, 12), pady=6)
        for group, keys in GROUPED.items():
            ctk.CTkLabel(panel, text=group.replace("MDI ", ""), anchor="w",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=("#6B4E2A", "#C9962A")).pack(fill="x", padx=4, pady=(8, 2))
            for key in keys:
                v = ctk.BooleanVar(value=False)
                ctk.CTkCheckBox(panel, text=f"{key} — {label_for(key)}", variable=v,
                                checkbox_width=16, checkbox_height=16).pack(fill="x", padx=8, pady=1)
                self._perm_vars[key] = v

    # -- data flow ----------------------------------------------------------
    def _reload(self) -> None:
        try:
            self.grid_widget.set_rows(self.service.list_users())
        except Exception as exc:
            self._error(str(exc).splitlines()[0])

    def _on_select(self, row: dict) -> None:
        code = str(row.get("code", "")).strip()
        full = self.service.get_user(code) or row
        self._editing = code
        self._set(self.code_entry, code)
        self.code_entry.configure(state="disabled")
        self._set(self.name_entry, str(full.get("name") or "").strip())
        self._set(self.pw_entry, "")
        for key, e in self._limit_entries.items():
            self._set(e, str(full.get(key) if full.get(key) is not None else "0"))
        granted = {p.strip().upper() for p in self.service.permissions_for(code)}
        for key, var in self._perm_vars.items():
            var.set(key in granted)
        self.status.configure(text=f"Editing {code}", text_color=("gray30", "gray70"))

    @staticmethod
    def _set(entry, value) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, str(value or ""))

    def _new(self) -> None:
        self._editing = None
        self._set(self.code_entry, "")
        self._set(self.name_entry, "")
        self._set(self.pw_entry, "")
        for e in self._limit_entries.values():
            self._set(e, "0")
        for var in self._perm_vars.values():
            var.set(False)
        self.grid_widget.clear_selection()
        self.status.configure(text="New user", text_color=("gray30", "gray70"))

    def _form(self) -> UserAccessForm:
        f = UserAccessForm(
            code=self.code_entry.get(), name=self.name_entry.get(), password=self.pw_entry.get(),
            permissions=[k for k, v in self._perm_vars.items() if v.get()],
        )
        for key, e in self._limit_entries.items():
            setattr(f, key, e.get() or "0")
        return f

    def _save(self) -> None:
        mode = "edit" if self._editing else "add"
        try:
            msg = self.service.save(self._form(), mode)
        except UserAccessError as exc:
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
            self._error("Select a user to delete")
            return
        if not messagebox.askyesno("Delete", f"Delete user '{code}'?"):
            return
        try:
            msg = self.service.delete(code)
        except UserAccessError as exc:
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
