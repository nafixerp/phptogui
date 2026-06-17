"""Application shell (customtkinter): sidebar nav + content area.

Sidebar is built from core.permissions.GROUPED (port of Permission::grouped()),
filtered by the signed-in user's access (AppSession.can / blocked_items). Only
Phase 1 items open real windows yet; the rest are disabled placeholders.

Company selector (top bar) lists databases and switches the active connection,
mirroring CompanySelectController behaviour at the DB layer.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from ..core.auth import AppSession, AuthService
from ..core.db import db
from ..core.permissions import GROUPED, label_for

# Permission keys that have a working Phase 1 window. Others are placeholders.
_IMPLEMENTED = {"MDI_DASHBOARD"}


class ShellFrame(ctk.CTkFrame):
    def __init__(self, master, auth: AuthService, session: AppSession, on_logout: Callable[[], None]):
        super().__init__(master, fg_color="transparent")
        self.auth = auth
        self.session = session
        self.on_logout = on_logout

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_topbar()
        self._build_sidebar()
        self.content = ctk.CTkScrollableFrame(self)
        self.content.grid(row=1, column=1, sticky="nsew", padx=(0, 10), pady=(0, 10))
        self.content.grid_columnconfigure(0, weight=1)
        self._show_dashboard()

    # -- top bar ------------------------------------------------------------
    def _build_topbar(self) -> None:
        bar = ctk.CTkFrame(self, corner_radius=0)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar, text="  GoldApp Desktop", font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, padx=10, pady=8)

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=2, padx=10, pady=6, sticky="e")

        ctk.CTkLabel(right, text="Company:").pack(side="left", padx=(0, 4))
        self.company_var = ctk.StringVar(value=self.session.selected_database)
        try:
            companies = db().list_databases()
        except Exception:
            companies = [self.session.selected_database]
        self.company_menu = ctk.CTkOptionMenu(
            right, values=companies or [self.session.selected_database],
            variable=self.company_var, command=self._switch_company, width=140,
        )
        self.company_menu.pack(side="left", padx=(0, 12))

        badge = f"{self.session.user_name or self.session.user_code}"
        if self.session.readonly:
            badge += "  [READ-ONLY]"
        ctk.CTkLabel(right, text=badge).pack(side="left", padx=(0, 10))
        ctk.CTkButton(right, text="Logout", width=80, command=self._logout).pack(side="left")

    # -- sidebar ------------------------------------------------------------
    def _build_sidebar(self) -> None:
        side = ctk.CTkScrollableFrame(self, width=260, label_text="Menu")
        side.grid(row=1, column=0, sticky="nsw", padx=10, pady=(0, 10))

        for group, keys in GROUPED.items():
            allowed = [k for k in keys if self.session.can(k)]
            if not allowed:
                continue
            ctk.CTkLabel(
                side, text=group.replace("MDI ", ""), anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("#6B4E2A", "#C9962A"),
            ).pack(fill="x", padx=4, pady=(10, 2))
            for key in allowed:
                implemented = key in _IMPLEMENTED
                ctk.CTkButton(
                    side, text=label_for(key), anchor="w", height=26,
                    fg_color="transparent", text_color=("gray10", "gray90"),
                    hover_color=("gray80", "gray30"),
                    state="normal" if implemented else "disabled",
                    command=(self._show_dashboard if key == "MDI_DASHBOARD"
                             else lambda k=key: self._placeholder(k)),
                ).pack(fill="x", padx=4)

    # -- content panes ------------------------------------------------------
    def _clear_content(self) -> None:
        for w in self.content.winfo_children():
            w.destroy()

    def _show_dashboard(self) -> None:
        self._clear_content()
        cc = self.session.currency_config or {}
        allowed = sum(1 for k in (x for keys in GROUPED.values() for x in keys) if self.session.can(k))
        lines = [
            ("Welcome", f"{self.auth.greeting()}, {self.session.user_name or self.session.user_code}"),
            ("User code", self.session.user_code),
            ("Company DB", self.session.selected_database),
            ("Read-only", "Yes" if self.session.readonly else "No"),
            ("Menu items allowed", str(allowed)),
            ("Menu items blocked", str(len(self.session.blocked_items))),
            ("Currency", f"{cc.get('currency_symbol', '₹')} {cc.get('currency_code', 'INR')}"),
            ("Login time", self.session.login_time.strftime("%Y-%m-%d %H:%M:%S")),
        ]
        ctk.CTkLabel(
            self.content, text="Dashboard", font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))
        card = ctk.CTkFrame(self.content)
        card.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        card.grid_columnconfigure(1, weight=1)
        for i, (k, v) in enumerate(lines):
            ctk.CTkLabel(card, text=k, anchor="w", font=ctk.CTkFont(weight="bold")).grid(
                row=i, column=0, sticky="w", padx=12, pady=4
            )
            ctk.CTkLabel(card, text=str(v), anchor="w").grid(row=i, column=1, sticky="w", padx=12, pady=4)

    def _placeholder(self, key: str) -> None:
        self._clear_content()
        ctk.CTkLabel(
            self.content, text=label_for(key), font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            self.content,
            text=f"'{key}' is not ported yet. It will be implemented in its build-order phase.",
            wraplength=600,
        ).grid(row=1, column=0, sticky="w", padx=16)

    # -- actions ------------------------------------------------------------
    def _switch_company(self, database: str) -> None:
        db().use_database(database)
        ok, _ = db().check_connection()
        if ok:
            self.session.selected_database = database
        else:  # revert selection on failure
            db().use_database(self.session.selected_database)
            self.company_var.set(self.session.selected_database)
        self._show_dashboard()

    def _logout(self) -> None:
        self.auth.record_logout(self.session)
        self.on_logout()
