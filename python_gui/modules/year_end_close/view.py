"""Year End Account Close window — destructive period close (confirmation-gated)."""
from __future__ import annotations

import customtkinter as ctk

from ...core.auth import AppSession
from ...core.db import Database
from .service import YearEndCloseError, YearEndCloseService

# (key, label) grouped exactly as the Laravel sections().
_DELETE_ITEMS = [
    ("chsales", "Delete Cash Sales"), ("crsales", "Delete Credit Sales"),
    ("sret", "Delete Sales Return"), ("chpurchase", "Delete Cash Purchase"),
    ("crpurchase", "Delete Credit Purchase"), ("purchaseret", "Delete Purchase Return"),
    ("otheritemtran", "Delete Other Item Transactions"), ("order", "Delete Order"),
    ("orderpend", "Delete Pending Order"), ("reppend", "Delete Pending Repair"),
    ("repr", "Delete Repair"), ("smith", "Delete Smith/Jewl/Dep Entries"),
    ("refn", "Delete Refinery Entries (closed)"), ("refnpend", "Delete Refinery Entries (pending)"),
    ("adjustment", "Delete Item Adjustment Entries"), ("kuricolln", "Delete Kuri/Scheme Colln Entries"),
    ("partnersdeposit", "Delete Partners Deposit Entries"),
]
_RESET_ITEMS = [
    ("deldaybookentries", "Delete Daybook Entries"), ("keepbills", "Keep Bills"),
    ("keeppendbills", "Keep Pending Bills"), ("dontsp", "Don't Close Sp. Accounts"),
    ("initopbalie", "Initialise Op. Balance of Income/Expense A/cs"),
    ("initopbalal", "Initialise Op. Balance of Assets/Liabilities"),
    ("initopstock", "Initialise Op. Stock Details"),
    ("initpartyopwgt", "Initialise Party Op. Wgt Details"),
    ("initsmithjewlopbal", "Initialise Smith/Jewl Op. Bal Details"),
    ("removeaddr", "Remove Addr+Phone from Clients"),
    ("deloutstockbarcode", "Delete Outstock Barcodes"),
]


class YearEndAccountCloseView(ctk.CTkFrame):
    TITLE = "Year End Account Close"

    def __init__(self, master, database: Database, session: AppSession):
        super().__init__(master, fg_color="transparent")
        self.service = YearEndCloseService(database, session)
        self._vars: dict[str, ctk.BooleanVar] = {}
        self._confirmed = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=self.TITLE, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(self, text="DESTRUCTIVE: permanently deletes transactions up to the closing date and "
                                "rolls forward opening balances/stock. This cannot be undone.",
                     text_color="#C0392B", anchor="w", justify="left", wraplength=720).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=4)
        ctk.CTkLabel(bar, text="Closing date (YYYY-MM-DD)").pack(side="left", padx=(0, 8))
        self.close_date = ctk.CTkEntry(bar, width=160); self.close_date.pack(side="left")

        left = ctk.CTkScrollableFrame(self, label_text="Delete Transactions", height=320)
        left.grid(row=3, column=0, sticky="nsew", padx=(12, 6), pady=6)
        right = ctk.CTkScrollableFrame(self, label_text="Close / Reset", height=320)
        right.grid(row=3, column=1, sticky="nsew", padx=(6, 12), pady=6)
        self.grid_rowconfigure(3, weight=1)
        for key, label in _DELETE_ITEMS:
            self._add_check(left, key, label)
        for key, label in _RESET_ITEMS:
            self._add_check(right, key, label)

        self.run_btn = ctk.CTkButton(self, text="Confirm & Close Accounts", fg_color="#922B21",
                                     hover_color="#7B241C", command=self._run)
        self.run_btn.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=10)
        self.status = ctk.CTkLabel(self, text="Select options, set the closing date, then press once to "
                                              "arm and again to run.", anchor="w", justify="left", wraplength=720)
        self.status.grid(row=5, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))

    def _add_check(self, parent, key, label):
        var = ctk.BooleanVar(value=False)
        self._vars[key] = var
        ctk.CTkCheckBox(parent, text=label, variable=var, command=self._reset_arm).pack(anchor="w", padx=6, pady=3)

    def _reset_arm(self):
        if self._confirmed:
            self._confirmed = False
            self.run_btn.configure(text="Confirm & Close Accounts")
            self.status.configure(text="Selection changed — press to arm again.", text_color="#B9770E")

    def _run(self):
        date = (self.close_date.get() or "").strip()
        if not date:
            self.status.configure(text="Closing date is required.", text_color="#C0392B"); return
        flags = {k: bool(v.get()) for k, v in self._vars.items()}
        if not any(flags.values()):
            self.status.configure(text="Select at least one option.", text_color="#C0392B"); return
        if not self._confirmed:
            self._confirmed = True
            self.run_btn.configure(text="ARMED — press again to RUN")
            self.status.configure(text=f"Armed for {date}. Press the button once more to execute the close.",
                                  text_color="#B9770E")
            return
        self.run_btn.configure(state="disabled")
        try:
            res = self.service.close_accounts(date, flags)
        except (YearEndCloseError, Exception) as exc:
            self.status.configure(text=f"Close failed: {str(exc).splitlines()[0]}", text_color="#C0392B")
            self.run_btn.configure(state="normal", text="Confirm & Close Accounts")
            self._confirmed = False
            return
        parts = ", ".join(f"{k}={v}" for k, v in res["summary"].items()) or "no rows affected"
        self.status.configure(text=f"Year-end close completed for {res['close_date']}. Summary: {parts}.",
                              text_color="#1E8449")
        self.run_btn.configure(state="normal", text="Confirm & Close Accounts")
        self._confirmed = False
