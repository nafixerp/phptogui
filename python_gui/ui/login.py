"""Login window (customtkinter).

Mirrors resources/views/native/login.blade.php: a single password field, shop
name + time-of-day greeting, and an error line. Authentication is delegated to
core.auth.AuthService (password-only legacy login).
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from ..core.auth import AppSession, AuthError, AuthService
from ..core.db import db


class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, auth: AuthService, on_success: Callable[[AppSession], None]):
        super().__init__(master, fg_color="transparent")
        self.auth = auth
        self.on_success = on_success

        shop = auth.shop_info()
        ok, conn_msg = db().check_connection()

        wrap = ctk.CTkFrame(self, corner_radius=16)
        wrap.place(relx=0.5, rely=0.5, anchor="center")
        wrap.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            wrap, text=shop["name"], font=ctk.CTkFont(size=24, weight="bold")
        ).grid(row=0, column=0, padx=48, pady=(36, 2), sticky="ew")

        ctk.CTkLabel(
            wrap, text=f"{auth.greeting()} — please sign in",
            font=ctk.CTkFont(size=14), text_color=("#6B4E2A", "#C9962A"),
        ).grid(row=1, column=0, padx=48, pady=(0, 20), sticky="ew")

        ctk.CTkLabel(wrap, text="Password", anchor="w").grid(
            row=2, column=0, padx=48, sticky="ew"
        )
        self.pw = ctk.CTkEntry(wrap, show="•", width=320, placeholder_text="Enter your password")
        self.pw.grid(row=3, column=0, padx=48, pady=(4, 8), sticky="ew")
        self.pw.bind("<Return>", lambda _e: self._submit())
        self.pw.focus_set()

        self.show_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            wrap, text="Show password", variable=self.show_var, command=self._toggle_pw,
            checkbox_width=18, checkbox_height=18,
        ).grid(row=4, column=0, padx=48, pady=(0, 12), sticky="w")

        self.error = ctk.CTkLabel(wrap, text="", text_color="#C0392B", wraplength=320)
        self.error.grid(row=5, column=0, padx=48, sticky="ew")

        self.btn = ctk.CTkButton(wrap, text="Sign In", width=320, command=self._submit)
        self.btn.grid(row=6, column=0, padx=48, pady=(6, 10), sticky="ew")

        status_color = ("#2E7D32" if ok else "#C0392B")
        ctk.CTkLabel(
            wrap, text=("● " + conn_msg), text_color=status_color,
            font=ctk.CTkFont(size=11), wraplength=320,
        ).grid(row=7, column=0, padx=48, pady=(0, 30), sticky="ew")

    def _toggle_pw(self) -> None:
        self.pw.configure(show="" if self.show_var.get() else "•")

    def _submit(self) -> None:
        self.error.configure(text="")
        self.btn.configure(state="disabled", text="Signing in…")
        self.update_idletasks()
        try:
            session = self.auth.authenticate(self.pw.get())
        except AuthError as exc:
            self.error.configure(text=str(exc))
            self.btn.configure(state="normal", text="Sign In")
            self.pw.delete(0, "end")
            self.pw.focus_set()
            return
        except Exception as exc:  # connection / driver errors
            self.error.configure(text=f"Login failed: {str(exc).splitlines()[0]}")
            self.btn.configure(state="normal", text="Sign In")
            return
        self.on_success(session)
