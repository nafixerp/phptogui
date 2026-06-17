"""Phone Book window (customtkinter) — read-only party directory.

Equivalent of phone-book.index: type + contact-status filters, search, a
summary strip (total / with mobile / phone / email), and the contact grid.
"""

from __future__ import annotations

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from ..widgets.datagrid import DataGrid
from .repo import PhoneBookRepo
from .service import CONTACT_STATUS, TYPES, PhoneBookService


class PhoneBookView(ctk.CTkFrame):
    TITLE = "Phone Book"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = PhoneBookService(PhoneBookRepo(database))

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(head, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")

        self.type_var = ctk.StringVar(value="C")
        ctk.CTkOptionMenu(head, width=130, variable=self.type_var,
                          values=[c for c, _ in TYPES], command=lambda _v: self._reload()).pack(side="left", padx=8)
        self.status_var = ctk.StringVar(value="all")
        ctk.CTkOptionMenu(head, width=140, variable=self.status_var,
                          values=CONTACT_STATUS, command=lambda _v: self._reload()).pack(side="left")

        self.search_var = ctk.StringVar()
        e = ctk.CTkEntry(head, width=200, placeholder_text="Search…", textvariable=self.search_var)
        e.pack(side="right")
        e.bind("<Return>", lambda _ev: self._reload())
        ctk.CTkButton(head, text="Search", width=70, command=self._reload).pack(side="right", padx=6)

        self.summary_lbl = ctk.CTkLabel(self, text="", anchor="w")
        self.summary_lbl.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))

        self.grid_widget = DataGrid(
            self,
            columns=[("code", "Code", 80), ("name", "Name", 200), ("type_label", "Type", 90),
                     ("mobile", "Mobile", 110), ("telephone", "Phone", 110), ("city", "City", 110)],
            key_field="code",
        )
        self.grid_widget.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self._reload()

    def _reload(self) -> None:
        try:
            ctype = self.type_var.get()
            search = self.search_var.get()
            rows = self.service.list_contacts(ctype, search, self.status_var.get())
            self.grid_widget.set_rows(rows)
            s = self.service.summary(ctype, search)
            self.summary_lbl.configure(
                text=f"Total: {s['total']}    With Mobile: {s['with_mobile']}    "
                     f"With Phone: {s['with_phone']}    With Email: {s['with_email']}"
            )
        except Exception as exc:
            self.summary_lbl.configure(text=str(exc).splitlines()[0], text_color="#C0392B")
