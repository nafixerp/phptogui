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
| 1 | Application settings | `ApplicationSettingsController` | ⏳ pending |
| 1 | User access editor | `UserAccessController` | ⏳ pending |
| 2 | Masters | `ItemMasterController` … | ⏳ |
| 3 | Parties | `NativeCustomerController` … | ⏳ |
| 4 | Accounting core | `docs/accounting-posting-logic.md` | ⏳ riskiest |
| 5 | Sales | `SalesBillController` … | ⏳ |
| 6 | Purchase | `PurchaseBillController` … | ⏳ |
| 7 | Inventory/Barcode | `StockController`, `Barcode*` | ⏳ |
| 8 | Orders | `OrderBillController` … | ⏳ |
| 9 | Schemes/Goldsmith/Staff | `Kuri*`, `Smith*`, `Staff*` | ⏳ |
| 10 | Compliance/Integration | `Gstr*`, `EInvoice*`, `Tally*` | ⏳ |

## Notes

- The sandbox where this scaffold was built has **no MySQL server**, so the live
  login screenshot can't be produced here — the login UI shows a red/green DB
  status line and authenticates as soon as it can reach the `demo` DB on a
  machine with XAMPP running. The crypto parity (the only part that can silently
  break auth) is proven above against PHP.
- `Decimal` everywhere for money/weight — never `float` (HARD RULE 3).
