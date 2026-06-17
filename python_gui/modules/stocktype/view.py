"""Stock Type window (customtkinter).

Equivalent of resources/views/stocktype/index.blade.php: a list of stock types
plus an add/edit form with Default + Compare flags. CRUD goes through
StockTypeService; the destroy decision tree maps to confirm/blocked dialogs.
"""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import StockTypeRepo
from .service import (
    ConfirmRequired,
    DeleteBlocked,
    StockTypeForm,
    StockTypeService,
    ValidationError,
)


class StockTypeView(ctk.CTkFrame):
    TITLE = "Stock Type"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = StockTypeService(StockTypeRepo(database), session)
        self._editing: str | None = None  # code being edited, or None for new

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8)
        )

        if not self.service.repo.table_exists():
            ctk.CTkLabel(
                self, text="The 'stktype' table was not found in this database.",
                text_color="#C0392B",
            ).grid(row=1, column=0, padx=12, sticky="w")
            return

        self.grid = DataGrid(
            self,
            columns=[("code", "Code", 90), ("name", "Name", 220),
                     ("def", "Default", 80), ("compare", "Compare", 80)],
            on_select=self._on_select, key_field="code",
        )
        self.grid.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)

        self._build_form()
        self._reload()

    # -- form ---------------------------------------------------------------
    def _build_form(self) -> None:
        form = ctk.CTkFrame(self, width=300)
        form.grid(row=1, column=1, sticky="ns", padx=(6, 12), pady=6)

        ctk.CTkLabel(form, text="Code").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 0))
        self.code_entry = ctk.CTkEntry(form, width=160)
        self.code_entry.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))

        ctk.CTkLabel(form, text="Name").grid(row=2, column=0, sticky="w", padx=12)
        self.name_entry = ctk.CTkEntry(form, width=240)
        self.name_entry.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 8))

        self.def_var = ctk.BooleanVar(value=False)
        self.compare_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(form, text="Default", variable=self.def_var).grid(
            row=4, column=0, sticky="w", padx=12, pady=4
        )
        ctk.CTkCheckBox(form, text="Compare", variable=self.compare_var).grid(
            row=5, column=0, sticky="w", padx=12, pady=4
        )

        btns = ctk.CTkFrame(form, fg_color="transparent")
        btns.grid(row=6, column=0, sticky="w", padx=12, pady=(12, 12))
        ctk.CTkButton(btns, text="New", width=70, command=self._new).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Save", width=70, command=self._save).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Delete", width=70, fg_color="#B03A2E",
                      hover_color="#943126", command=self._delete).pack(side="left")

        self.status = ctk.CTkLabel(form, text="", wraplength=260)
        self.status.grid(row=7, column=0, sticky="w", padx=12, pady=(0, 12))

    # -- data flow ----------------------------------------------------------
    def _reload(self) -> None:
        try:
            self.grid.set_rows(self.service.list())
        except Exception as exc:
            self._error(str(exc).splitlines()[0])

    def _on_select(self, row: dict) -> None:
        self._editing = str(row.get("code", ""))
        self.code_entry.configure(state="normal")
        self.code_entry.delete(0, "end")
        self.code_entry.insert(0, str(row.get("code", "")))
        self.code_entry.configure(state="disabled")   # code is the key; not editable on edit
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, str(row.get("name", "")))
        self.def_var.set(bool(row.get("def")))
        self.compare_var.set(bool(row.get("compare")))
        self.status.configure(text=f"Editing {self._editing}", text_color=("gray30", "gray70"))

    def _new(self) -> None:
        self._editing = None
        self.code_entry.configure(state="normal")
        self.code_entry.delete(0, "end")
        self.name_entry.delete(0, "end")
        self.def_var.set(False)
        self.compare_var.set(False)
        self.grid.clear_selection()
        self.status.configure(text="New stock type", text_color=("gray30", "gray70"))
        self.code_entry.focus_set()

    def _form(self) -> StockTypeForm:
        return StockTypeForm(
            code=self.code_entry.get(),
            name=self.name_entry.get(),
            def_=self.def_var.get(),
            compare=self.compare_var.get(),
        )

    def _save(self) -> None:
        try:
            if self._editing:
                saved = self.service.update(self._editing, self._form())
            else:
                saved = self.service.create(self._form())
        except ValidationError as exc:
            self._error(str(exc))
            return
        except Exception as exc:
            self._error(str(exc).splitlines()[0])
            return
        self._reload()
        code = str(saved.get("code", ""))
        self.grid.select_key(code)
        self._editing = code
        self.code_entry.configure(state="disabled")
        self.status.configure(text=f"Saved {code}", text_color="#1E8449")

    def _delete(self) -> None:
        code = (self.code_entry.get() or "").strip().upper()
        if not code:
            self._error("Select a stock type to delete")
            return
        if not messagebox.askyesno("Delete", f"Delete stock type '{code}'?"):
            return
        try:
            self.service.delete(code)
        except ConfirmRequired as exc:
            if messagebox.askyesno("Confirm", str(exc)):
                try:
                    self.service.delete(code, force=True)
                except Exception as e2:
                    self._error(str(e2).splitlines()[0])
                    return
            else:
                return
        except DeleteBlocked as exc:
            messagebox.showwarning("Cannot delete", str(exc))
            return
        except (ValidationError, Exception) as exc:
            self._error(str(exc).splitlines()[0])
            return
        self._new()
        self._reload()
        self.status.configure(text=f"Deleted {code}", text_color="#1E8449")

    def _error(self, msg: str) -> None:
        self.status.configure(text=msg, text_color="#C0392B")
