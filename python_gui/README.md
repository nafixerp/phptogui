# GoldApp Desktop (Python GUI)

A native **Python desktop** port of the Laravel GoldApp jewellery/gold-shop ERP.
It runs against the **same, frozen MySQL schema** as the PHP app — no migrations,
no renamed columns, no new tables. Both apps can run side-by-side during the
migration.

- **GUI:** customtkinter (Tkinter)
- **DB:** SQLAlchemy Core + mysql-connector-python (raw parameterised SQL)
- **Config:** reads the existing Laravel `.env` (never hardcoded)
- **Auth:** reuses the legacy `userm` / `userd` / `userhist` tables and the exact
  legacy password hashing — existing users are **not** reset
- **Print:** reportlab (added per-module from Phase 5)
- **Packaging:** PyInstaller one-folder (Windows `.exe`)

## Layout

```
python_gui/
  main.py              # bootstrap: theme -> login -> shell
  core/
    config.py          # parse ../.env (Laravel)            [done]
    db.py              # SQLAlchemy engine + company switch  [done]
    crypto.py          # legacy fpCrypt password hash        [done, parity-proven]
    auth.py            # legacy login + permissions + history[done]
    permissions.py     # MDI menu map (Permission::grouped)  [done]
    decimals.py        # money/weight Decimal helpers         [done]
    pdf.py             # reportlab print base                 [stub]
  ui/
    login.py           # password-only login window          [done]
    shell.py           # sidebar nav + company selector       [done]
    widgets/           # reusable grid/date/party pickers      [later]
  modules/<module>/    # view.py + service.py + repo.py per module
  tools/parity_check.py# PHP-vs-Python crypto parity proof    [done]
  tests/test_crypto.py # pinned reference vectors             [done]
```

## Run

```bash
pip install -r python_gui/requirements.txt
# from the repo root (python_gui must sit inside / beside the Laravel root so
# ../.env is found; or set GOLDAPP_ENV=/path/to/.env)
python -m python_gui.main
```

`core/config.py` looks for `.env` at, in order: `$GOLDAPP_ENV`, `../.env`,
`../extracted/.env`, `python_gui/.env`, `../../.env`.

## Windows install / run / package

Double-clickable scripts live in `python_gui/`:

| Script | Purpose |
|--------|---------|
| `install.bat` | Finds Python 3.11+, creates a `.venv` beside the package, installs `requirements.txt`. Run once per machine. |
| `run.bat` | Launches the app via the venv (`python -m python_gui.main`). |
| `build.bat` | Builds a standalone `dist\GoldApp\GoldApp.exe` with PyInstaller (uses `goldapp.spec`). |
| `goldapp.spec` | PyInstaller one-folder spec; entry point is `launch.py`, bundles customtkinter assets + mysql/sqlalchemy/reportlab hidden imports. |
| `launch.py` | Frozen-app entry: puts the repo root on `sys.path` then starts the package (works around `main.py`'s relative imports). |

The `.env` is **never** bundled — keep it beside `GoldApp.exe` or set `GOLDAPP_ENV`.

## Parity proof (Phase 1 — auth)

Login matches a `userm` row on `UPPER(HEX(pcode))`. The hash must therefore be
**byte-identical** to PHP. Verified against the real PHP algorithm:

```bash
python -m python_gui.tools.parity_check     # requires php on PATH; exit 0 = identical
python -m pytest python_gui/tests            # pinned reference vectors
```

Result: all vectors (ASCII + multibyte) identical → a Python login authenticates
existing users without touching the password tables.

## Per-module parity status

| Phase | Module | Laravel source | Status |
|------|--------|----------------|--------|
| 1 | Shell: config/.env loader | `config/database.php`, `.env` | ✅ done |
| 1 | Shell: DB connect + company switch | `CompanySelectController` | ✅ core done |
| 1 | Shell: legacy login | `NativeAuthController`, `UserM`, `PasswordService` | ✅ done (parity-proven) |
| 1 | Shell: permissions | `Enums/Permission`, `userd` | ✅ map + enforcement done |
| 1 | Shell: dashboard + sidebar | `NativeDashboardController` | ✅ scaffold |
| 1 | **User access editor** | `UserAccessController` | ✅ done (userm+userd, login round-trip tested) |
| 1 | **Application settings** | `ApplicationSettingsController` | ✅ done (DB-backed shop info + counters) |
| 2 | **Stock Type** master | `StockTypeController`, `StockType` | ✅ done (repo+service+view, tested) |
| 2 | **Masters**: group, sub-group, purity, counters, bill prefix, denomination, MC table | `ItemGroupController` … | ✅ done (tested) |
| 2 | **Item Master** | `ItemMasterController` | ✅ done (column-filtered payload, delete guards, rename cascade) |
| 2 | **Gift Table, Wastage Table, Point Card** | `GiftTableController`, `WastageTableController`, `PointCardController` | ✅ done (tested) |
| 2 | **Model Master, Party MC Table, Hallmark, Scale, Country/Currency** | `ModelMasterController` … | ✅ done (tested) |
| 3 | **Parties** (Customer/Supplier/Staff/…) | `NativeCustomerController` | ✅ core CRUD done (clients+accountm, tested) |
| 3 | **Phone book** (read-only directory) | `PhoneBookController` | ✅ done (tested) |
| 3 | **Party Opening Weight, Customer Op Bills, Party Reports, Secondary-DB Sync** | `PartyOpWeightController`, `CustomerOpBillsController`, `SecondaryDatabaseSync` | ✅ done (tested) |
| 4 | **Account Master** | `AccountMasterController` | ✅ done (accountm CRUD, tested) |
| 4 | **Posting engine + Receipt + Payment** | `ReceiptController`, `PaymentController` | ✅ done (zero-sum invariant tested) |
| 4 | **Journal, Ledger, Day Book/Summary, Cash/Bank Book, Debit/Credit Note, Expense Voucher** | `JournalController` … | ✅ done (tested) |
| 5 | **Sales** — bill+return+register+print, **reports (net/monthly/salesman/checklist) + confirmation** | `SalesBillController`, `SalesReturnController`, `*ReportController` | ✅ complete (tested) |
| 6 | **Purchase + Purchase Return** | `PurchaseBillController`, `PurchaseReturnController` | ✅ done — item grid + calc + return posting (zero-sum tested) |
| 6 | **Purchase reports (net/monthly/supplier/checklist) + Tax Purchase Book + Bill Confirmation** | `PurchaseBookController`, `TaxPurchaseBookController`, `PurchaseCheckListController`, `PurchaseBillConfirmationController` | ✅ done (column-guarded over `purchasem`; confirm flips `control 4→1` across related tables; tested) |
| 6 | **Diamond Purchase** (register + stone detail) | `DiamondPurchaseBillController` | ✅ register/load done (`pr='P' dmd='Y'` over `purchasem`/`purchased` + `purchased_dmddet` stone sub-rows grouped by `prow`; doc-no preview `DPBPREF`+`DPURCHASEB`; daybook reuses PL posting; tested) |
| 5/6 | **Sales/Purchase Registers** (+returns) + bill-print PDF base | `SalesRegisterController` …, `core/pdf.py` | ✅ done (tested) |
| 7 | **Barcode Entry/Stock List, Stock Register/Verification, Item Adjustment** | `Barcode*`, `StockRegisterController`, `StockVerificationController`, `ItemAdjustmentController` | ✅ done (tested) |
| 7 | **Barcode Profit, Marked List, Diamond/Stone Stock, Counter Issue, Reorder** | `BarcodeProfitReportController`, `MarkedListController`, `DiamondStoneStockController`, `CounterIssueController`, `ReorderController` | ✅ done (cost/profit rules, mark/type filters, in-stock stone aggregates, counter list, `rotable` replace + `models` register; tested) |
| 7 | **Stock movement engine + Stock Period Ledger + Stock Summary (cost/rate-wise) + Barcode History** | `StockPeriodLedgerController::calcItemStock`, `StockSummaryCostWise/RateWiseController`, `BarcodeHistoryController` | ✅ done (`core/stock.py` signed opening/issued/received/closing across sales/returns/purchase/smith/refinery/itemadj/orders; metal-split txn summary; per-barcode timeline; tested) |
| 8 | **Order Bill + Order Cancel** | `OrderBillController`, `OrderCancelController` | ✅ done (advance zero-sum + cancel/reverse tested) |
| 8 | **Order Rate Fix / Block + Order Process/Returns + Refinery Report + Repair Complaints** | `OrderRateFixController`, `OrderBlockController`, `OrderProcessController`, `OrderReturnsController`, `RefineryReportController`, `RepairComplaintsController` | ✅ done (returned-order guard on rate-fix/block; pending-process advance; order→sale returns; refinery forward/return register; `repcompl` dedup/replace; tested) |
| 9 | **Kuri Collection + Smith Book + Staff Transaction** | `KuriCollectionController`, `SmithController`, `StaffTransactionController` | ✅ done (zero-sum tested) |
| 9 | **Kuri Type Master + PDC Report + Smith Lot Report + Gold Loan** | `KuriTypeMasterController`, `PdcReportController`, `SmithLotReportController`, `GoldLoanController` | ✅ done (kuritype replace/column-filter + in-use guard; pdclist receipt/payment split + delete; smith lot issued/received/pending; loan+loan_items+loancolln load with balance — `loan*` tables confirmed present in demo; tested) |
| 9 | **Kuri Finish/Maturity + Kuri Interest Post + Order Profit Analysis** | `KuriFinishController`, `KuriIntPostController`, `OrderProfitAnalysisController` | ✅ done (KC-member maturity balance + est weight; simple interest on kuricolln entries, computed in Python so no MySQL `DATEDIFF`; order advance-vs-sold diff; tested). Deposit/Depositors-Int and Staff Payroll/Salary deferred — `depositm`/`staffmas`/`staffsal` absent from frozen demo. |
| 10 | **Tally Export + GST Summary** | `TallyExportController`, `GstrReportController` | ✅ done (tested) |
| 10 | **e-Invoice Register + Outstanding Tax + TDS Report + Purity Certificate** | `EInvoiceRegisterController`, `OutstandingTaxReportController`, `TdsReportController`, `PurityCertificateController` | ✅ done (e_invoices IRN ledger + detail; output/input GST+TCS net; smithm TDS; purity cert counter + item search; tested). Detailed GSTR B2B/B2C depends on the newer `sales_bills` table (absent from the frozen demo) — guarded follow-on. |

## Bucket A — analytical reports (in progress)

Long-tail read reports being ported in themed batches on top of the core.

| Group | Modules | Source | Status |
|------|---------|--------|--------|
| Accounts | **Chart of Accounts, Group Summary, Cash Balance** | `ChartOfAccountsController`, `CashBalanceController`, `AcSummaryController` group rollup | ✅ done (shared `opbal+Σdaybook` balance, as-of date, type/group filters; tested) |
| Items | **Itemwise Profit, Item Movement, Cost List** | `ItemwiseProfitController`, `ItemMovementController`, `ItemReportsController` | ✅ done (cost basis cost*qty when stkinnos='Y' else cost*weight; sr='S'/opbill guards; movement totals; master cost/rate list; tested) |

## Notes

- The sandbox where this scaffold was built has **no MySQL server**, so the live
  login screenshot can't be produced here — the login UI shows a red/green DB
  status line and authenticates as soon as it can reach the `demo` DB on a
  machine with XAMPP running. The crypto parity (the only part that can silently
  break auth) is proven above against PHP.
- `Decimal` everywhere for money/weight — never `float` (HARD RULE 3).
