"""GoldApp Desktop — application bootstrap.

Flow: theme -> login window -> (on success) application shell -> logout -> login.
Run from the repo root:  python -m python_gui.main
"""

from __future__ import annotations

import customtkinter as ctk

from .core.auth import AppSession, AuthService
from .core.config import config


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        cfg = config()
        self.title(f"{cfg.app_name} — Desktop")
        self.geometry("1100x720")
        self.minsize(900, 600)

        self.auth = AuthService()
        self._frame: ctk.CTkFrame | None = None
        self._show_login()

    def _swap(self, frame: ctk.CTkFrame) -> None:
        if self._frame is not None:
            self._frame.destroy()
        self._frame = frame
        self._frame.pack(fill="both", expand=True)

    def _show_login(self) -> None:
        from .ui.login import LoginFrame
        self._swap(LoginFrame(self, self.auth, on_success=self._show_shell))

    def _show_shell(self, session: AppSession) -> None:
        from .ui.shell import ShellFrame
        self._swap(ShellFrame(self, self.auth, session, on_logout=self._show_login))


def main() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    App().mainloop()


if __name__ == "__main__":
    main()
