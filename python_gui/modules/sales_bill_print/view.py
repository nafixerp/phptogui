"""Sales Bill Print window — enter a bill slno, generate + open the PDF."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from .service import SalesBillPrintError, SalesBillPrintService


def open_file(path: str) -> None:
    """Open a generated PDF with the OS default viewer (best-effort)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class SalesBillPrintView(ctk.CTkFrame):
    TITLE = "Sales Bill Print"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = SalesBillPrintService(database)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        ctk.CTkLabel(self, text="Bill slno").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        self.slno = ctk.CTkEntry(self, width=160); self.slno.grid(row=1, column=1, sticky="w", padx=12, pady=4)
        ctk.CTkButton(self, text="Generate PDF", command=self._print).grid(
            row=2, column=1, sticky="w", padx=12, pady=10)
        self.status = ctk.CTkLabel(self, text="", anchor="w"); self.status.grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=4)

    def _print(self):
        try:
            slno = int((self.slno.get() or "0").strip())
        except ValueError:
            self.status.configure(text="Enter a numeric slno", text_color="#C0392B"); return
        path = os.path.join(tempfile.gettempdir(), f"sales_bill_{slno}.pdf")
        try:
            self.service.render_pdf(slno, path)
        except (SalesBillPrintError, Exception) as exc:
            self.status.configure(text=str(exc).splitlines()[0], text_color="#C0392B"); return
        open_file(path)
        self.status.configure(text=f"Saved: {path}", text_color="#1E8449")
