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

# Permission keys with a working window. Others render as disabled placeholders.
# Value = dotted import path "module:ClassName" (imported lazily on open).
_MODULES: dict[str, str] = {
    "MDI_STOCK_TYPE": "python_gui.modules.stocktype.view:StockTypeView",
    "MDI_CUSTOMER": "python_gui.modules.parties.view:CustomerView",
    "MDI_SUPPLIER_MASTER": "python_gui.modules.parties.view:SupplierView",
    "MDI_ACCOUNTS_MASTER": "python_gui.modules.account_master.view:AccountMasterView",
    "MDI_ACCOUNTS_RECEIPT": "python_gui.modules.receipt.view:ReceiptView",
    "MDI_ACCOUNTS_PAYMENT": "python_gui.modules.payment.view:PaymentView",
    "MDI_ACCOUNTS_JOURNAL": "python_gui.modules.journal.view:JournalView",
    "MDI_ACCOUNTS_AC_LEDGER": "python_gui.modules.account_ledger.view:AccountLedgerView",
    "MDI_DAYBOOK": "python_gui.modules.day_book.view:DayBookView",
    "MDI_DAY_SUMMARY": "python_gui.modules.day_summary.view:DaySummaryView",
    "MDI_ACCOUNTS_DEBIT_CREDIT_NOTE": "python_gui.modules.debit_credit_note.view:DebitCreditNoteView",
    "MDI_ACCOUNTS_EXPENSE_VOUCHER_ENTRY": "python_gui.modules.expense_voucher.view:ExpenseVoucherView",
    "MDI_CASH_BOOK": "python_gui.modules.cash_bank_book.view:CashBookView",
    "MDI_BANK_BOOK": "python_gui.modules.cash_bank_book.view:BankBookView",
    "MDI_SALES_BILL": "python_gui.modules.sales.view:SalesView",
    "MDI_SALES_RETURN": "python_gui.modules.sales_return.view:SalesReturnView",
    "MDI_SALES_BILL_CONFIRMATION": "python_gui.modules.sales_confirmation.view:SalesConfirmationView",
    "MDI_SALES_BOOK_REPORT": "python_gui.modules.sales_reports.view:SalesReportsView",
    "MDI_NET_SALES_REPORT": "python_gui.modules.sales_reports.view:SalesReportsView",
    "MDI_MONTHLY_SALES_REPORT": "python_gui.modules.sales_reports.view:SalesReportsView",
    "MDI_SALES_CHECK_LIST": "python_gui.modules.sales_reports.view:SalesReportsView",
    "MDI_SALESMAN_CATEGORY_REPORT": "python_gui.modules.sales_reports.view:SalesReportsView",
    "MDI_PURCHASE_BILL": "python_gui.modules.purchase.view:PurchaseView",
    "MDI_PURCHASE_RETURN": "python_gui.modules.purchase_return.view:PurchaseReturnView",
    "MDI_PURCHASE_BILL_CONFIRMATION": "python_gui.modules.purchase_confirmation.view:PurchaseConfirmationView",
    "MDI_PURCHASE_BOOK": "python_gui.modules.purchase_reports.view:PurchaseReportsView",
    "MDI_TAX_PURCHASE_BOOK": "python_gui.modules.purchase_reports.view:PurchaseReportsView",
    "MDI_PURCHASE_CHECK_LIST": "python_gui.modules.purchase_reports.view:PurchaseReportsView",
    "MDI_DIAMOND_PURCHASE_BILL": "python_gui.modules.diamond_purchase.view:DiamondPurchaseView",
    "MDI_SALES_REGISTER": "python_gui.modules.registers.view:SalesRegisterView",
    "MDI_SALES_RETURN_REGISTER": "python_gui.modules.registers.view:SalesReturnRegisterView",
    "MDI_PURCHASE_REGISTER": "python_gui.modules.registers.view:PurchaseRegisterView",
    "MDI_PURCHASE_RETURN_REGISTER": "python_gui.modules.registers.view:PurchaseReturnRegisterView",
    "MDI_BARCODE_SINGLE_ENTRY": "python_gui.modules.barcode_entry.view:BarcodeEntryView",
    "MDI_STOCK_REGISTER": "python_gui.modules.stock_register.view:StockRegisterView",
    "MDI_ITEM_STOCK_ADJUSTMENT": "python_gui.modules.item_adjustment.view:ItemAdjustmentView",
    "MDI_BARCODE_REGISTER": "python_gui.modules.barcode_stock.view:BarcodeStockListView",
    "MDI_STOCK_VERIFICATION": "python_gui.modules.barcode_stock.view:StockVerificationView",
    "MDI_ORDER_BILL": "python_gui.modules.orders.view:OrderBillView",
    "MDI_ORDER_CANCEL": "python_gui.modules.order_cancel.view:OrderCancelView",
    "MDI_STAFF_TRANSACTION": "python_gui.modules.staff_transaction.view:StaffTransactionView",
    "MDI_SCHEME_COLLECTION": "python_gui.modules.kuri_collection.view:KuriCollectionView",
    "MDI_SMITH_BOOK": "python_gui.modules.smith_book.view:SmithBookView",
    "MDI_TALLY_EXPORT": "python_gui.modules.tally_export.view:TallyExportView",
    "MDI_GSTR_REPORTS": "python_gui.modules.gst_report.view:GstReportView",
    "MDI_PHONE_BOOK": "python_gui.modules.phonebook.view:PhoneBookView",
    "MDI_USER_ACCESS": "python_gui.modules.user_access.view:UserAccessView",
    "MDI_GROUPS": "python_gui.modules.item_group.view:ItemGroupView",
    "MDI_SUB_GROUPS": "python_gui.modules.item_subgroup.view:ItemSubGroupView",
    "MDI_PURITY_TYPE": "python_gui.modules.purity_type.view:PurityTypeView",
    "MDI_COUNTERS": "python_gui.modules.counters.view:CountersView",
    "MDI_BILL_PREFIX": "python_gui.modules.bill_prefix.view:BillPrefixView",
    "MDI_DENOMINATION_MASTER": "python_gui.modules.denomination.view:DenominationView",
    "MDI_MC_TABLE": "python_gui.modules.mctable.view:MCTableView",
    "MDI_GIFT_TABLE": "python_gui.modules.gift_table.view:GiftTableView",
    "MDI_WASTAGE_TABLE": "python_gui.modules.wastage_table.view:WastageTableView",
    "MDI_POINT_CARD": "python_gui.modules.point_card.view:PointCardView",
    "MDI_MODEL_MASTER": "python_gui.modules.model_master.view:ModelMasterView",
    "MDI_PARTY_MC_TABLE": "python_gui.modules.party_mctable.view:PartyMCTableView",
    "MDI_HALLMARK": "python_gui.modules.hallmark.view:HallmarkView",
    "MDI_SCALE_SETTINGS": "python_gui.modules.scale.view:ScaleView",
    "MDI_PARTY_OP_WEIGHT": "python_gui.modules.party_op_weight.view:PartyOpWeightView",
    "MDI_OP_BILL_CREATION_CUSTOMERS": "python_gui.modules.customer_op_bills.view:CustomerOpBillsView",
    "MDI_CUSTOMER_ANALYTICS": "python_gui.modules.party_reports.view:PartyReportsView",
    "MDI_ITEM_MASTER": "python_gui.modules.item_master.view:ItemMasterView",
    "MDI_APPLICATION_SETTINGS": "python_gui.modules.app_settings.view:AppSettingsView",
}
_IMPLEMENTED = {"MDI_DASHBOARD", *_MODULES.keys()}


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
        self.content = ctk.CTkFrame(self)
        self.content.grid(row=1, column=1, sticky="nsew", padx=(0, 10), pady=(0, 10))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)
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
                             else (lambda k=key: self._open_module(k)) if key in _MODULES
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

    def _open_module(self, key: str) -> None:
        import importlib

        self._clear_content()
        try:
            module_path, _, class_name = _MODULES[key].partition(":")
            view_cls = getattr(importlib.import_module(module_path), class_name)
            view = view_cls(self.content, db(), self.session)
            view.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=4, pady=4)
        except Exception as exc:
            ctk.CTkLabel(
                self.content, text=f"Failed to open {key}: {str(exc).splitlines()[0]}",
                text_color="#C0392B", wraplength=600,
            ).grid(row=0, column=0, sticky="w", padx=16, pady=16)

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
