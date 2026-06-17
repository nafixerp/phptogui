# Phase 3 — Parties — Module Map

Source of truth: `docs/customer-supplier-staff-create-logic.txt` +
`app/Http/Controllers/NativeCustomerController.php` (1586 lines).

All party types live in one table, `clients`, distinguished by `ctype`; the
matching account row is `accountm.accode = clients.code`.

| ctype | Party | Code prefix / counter | accountm actype1 / default group |
|---|---|---|---|
| C | Customer | CPREFIX / CLASTNO | A / SUNDB |
| S | Supplier | SPREFIX / SLASTNO | L / SUNCR |
| F | Staff | F / SLASTNO | L / SUNCR |
| D | Depositor (stored ctype=C, grp=DEP) | C / CLASTNO | A / SUNDB |
| G | Goldsmith | G / SLASTNO | L / SUNCR |
| R | Refiner | R / SLASTNO | L / SUNCR |
| J | Jewellery | J / SLASTNO | L / SUNDB |

| Module | Controller | View | Tables | Status |
|---|---|---|---|---|
| **Customer / Supplier / parties** ✅ | `NativeCustomerController` | `native/customer/form` | `clients`, `accountm`, `generals`, `generali`, `clients_advanced` | core CRUD done |
| Phone book | `PhoneBookController` | `phone-book` | phone book table | ⏳ next |
| Party opening weight | `PartyOpWeightController` | `party-op-weight` | clients/accountm weights | ⏳ |
| Customer opening bills | `CustomerOpBillsController` | `op-bill-creation/customers` | bills | ⏳ |
| Customer reports / campaign | `CustomerReportsController`, `CustomerCampaignController` | … | — | ⏳ |
| Supplier reports | `SupplierReportsController` | … | — | ⏳ |

## Customer save — extracted rules (parity reference)

`buildClientRow()` (NativeCustomerController.php:795):
- `name` = UPPER+TRIM, substr 40. addr1/2/3 via `normalizeAddressLines` (re-wrap
  to ≤30 chars), then UPPER. city/pin/state/pan/tin/cst/cocode/grp/route/carea/
  idno/religion/note/pcard/smcode/pcardno = UPPER. phone/mobile/email/pospwd/
  homemobile = TRIM only.
- **Sign convention:** `opbalance/opbalanceb/opweight/opdepwgtbal` →
  `credit = +abs`, `debit = -abs`. `grp` default `'O'`. checkboxes
  (removed/blocked/coparty/agent/approval) → 1/0 or Y/N.
- Candidate row is **filtered to the real `clients` columns** (so e.g. `blocked`
  is dropped — `clients` has no such column on the frozen schema).

`upsertAccountM()` (NativeCustomerController.php:1344):
- `name` = `(clientName + "(code)")[:30]`; `actype1` = A if ctype=C else L;
  default group SUNDB if ctype∈{C,D,J} else SUNCR; `grcode` =
  payload.acgrp ?? clients.grp ?? default (so usually `'O'`); `bshead`/`shedgrp`
  follow grcode; hlp=1, sp=0. Column-filtered, upsert by `accode`.

Code generation:
- `getNextAutoCode` (suggestion, no write) / `reserveNextCode` (writes the
  `generali` counter). Number = `max(counter, max existing PREFIX<digits>) + 1`,
  zero-padded to 4. `syncCodeCounter` bumps the counter when a manual numeric
  code ≥ counter is saved (C/S/F only).

Validation: name required; Customer & Depositor require phone OR mobile
(Supplier/Staff do not). Rename allowed only if no linked transactions
(`daybook/daybookpart/daybookratewgt/oglist/accode`, `salesm/orderm/custcode`).
Delete blocked if `daybook.accode` exists.

## Parity status

- Pure helpers (date/address/sign), code generation, buildClientRow &
  accountm builders, save validation/flow: unit-tested headless
  (`tests/test_parties_service.py`, 19 cases).
- Repo SQL (insert/update clients, upsert accountm, generali updateOrInsert,
  transaction): executed against a live SQL engine.
- Live `demo` before/after proof: pending a MySQL host.

## Deferred (flagged — not in the core clients/accountm save)

- Goldsmith/Refiner/Jewellery weight tab → `clientsgs` (G/R/J only).
- `clients_advanced` extra fields (repo write method ready; form not yet wired).
- Photo upload (`clientspict`), CSV import, and background **secondary-DB sync**
  (`deom12`, gated by `ALLOWSECONDARYDBSYNC` + SecondaryDatabaseSync).
