# Phase 4 — Accounting Core — Module Map

**Riskiest phase.** Source of truth: `docs/accounting-posting-logic.md` +
`docs/transaction-create-posting-logic.txt`. Every posting must keep the
double-entry invariant: a complete `slno` group in `daybook` sums to zero, and
every posted `accode` exists in `accountm`.

## The ledger tables (frozen)
- `daybook(slno, sno, tdate, accode, amount, control, opaccode)` — signed ledger.
  **Negative amount = debit, positive = credit.**
- `daybookpart(slno, vchno, particular, staff, chequeno/date, duedate, …)` —
  voucher header/narration per slno.
- `daybookratewgt(slno, rate, mcp, wgt, code, tdate, control)` — rate/weight.
- `accountm` master (actype1 R/E/A/L; actype2 H=cash B=bank C/S/G/R/J=party).

## Build order within Phase 4 (one at a time)
| # | Module | Controller | Status |
|---|--------|-----------|--------|
| 1 | **Account Master** | `AccountMasterController` | ✅ done (accountm CRUD) |
| 2 | Account groups + BS heads | `AccountMasterController` (apiGroups/apiBSHeads) | ⏳ (read-only lists wired) |
| 3 | **Posting engine** (slno reserve, vchno, daybook/daybookpart writer) | shared | ⏳ next — foundation for 4–8 |
| 4 | Receipt voucher | `ReceiptController` | ⏳ |
| 5 | Payment voucher | `PaymentController` | ⏳ |
| 6 | Journal | `JournalController` | ⏳ |
| 7 | Account Ledger (report) | `AccountLedgerController` | ⏳ |
| 8 | Day Book / Cash / Bank book | `DayBookController`, `CashBookController`, `BankBookController` | ⏳ |

## Account Master — extracted rules (done; parity reference)

`saveAccountInternal()` / `validateAccount()` / `deleteAccountInternal()`:
- Required: accode, desc, group. `bshead` required when actype1 ∈ {A,L}.
  actype1 must be R/E/A/L.
- **Opening balance sign:** `normalizeAmount` → abs, **debit = negative, credit
  = positive**. Active column `opbal` at gilevel 1 else `opbalb` (demo = level 1).
- Flags: control = display?1:2; hlp = hlp?0:1; reserve/blocked Y/N; sp/removed 1/0.
  `shedgrp` defaults to accode. Row is column-filtered to `accountm`.
- Edit (mode E): `MASTEREDIT` permission blocks edit; rename allowed only if the
  new code is free AND `daybook` has no rows for the old code; on rename, cascade
  `accountm.shedgrp` references to the new code.
- Delete: blocked for reserved accounts, party-linked accounts (actype2 ∈
  C/S/G/R/J — managed via party master), and accounts with daybook transactions
  (`SUM(ABS(amount)) > 0`).

## Posting engine — plan (next module, before any voucher)

A shared `modules/accounts_posting/` with:
- **Serial reservation** — `generali.SERIALNO`, but also scan max `slno` across
  `salesm/salesrm/purchasem/purchaserm/daybook/daybookpart/orderm/smithm/
  refinerym/repairm` and take max+1 (per the doc).
- **Voucher numbering** — receipt VRB//VRE//VRB//VRC/, payment VPB//VPE//…,
  journal JL…, PDC PDCR//PDCP/; counters in `generali`, de-duped against
  `daybookpart.vchno`.
- **daybook/daybookpart writer** — insert header + signed lines, column-filtered;
  after insert, sum `daybook.amount` for the slno and add a `ROUND` line for the
  negative remainder when non-zero (sales/purchase). Assert zero-sum.
- **Voucher delete** — remove `daybook` + `daybookpart` (+ `pdclist`,
  `daybookratewgt`) for the slno.

This will be unit-tested for the zero-sum invariant before Receipt is built.

## Parity status (Account Master)
- Save validation, sign convention, edit/rename + delete guards, load→form
  mapping: unit-tested headless (`tests/test_account_master_service.py`, 14 cases).
- Repo SQL (insert/load/rename + shedgrp cascade/tx-guard/delete/lists):
  executed on a live SQL engine.
- Live `demo` before/after proof: pending a MySQL host.
