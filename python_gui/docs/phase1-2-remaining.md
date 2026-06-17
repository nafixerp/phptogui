# Phase 1 & Phase 2 — remaining modules

Status snapshot (after User Access).

## Phase 1 — Shell
| Module | Controller | Status |
|---|---|---|
| .env loader / DB connect | config/database.php | ✅ done |
| Legacy login | NativeAuthController | ✅ done (parity-proven) |
| Dashboard + sidebar nav | NativeDashboardController | ✅ scaffold |
| Permissions enforcement | Enums/Permission, userd | ✅ done |
| Company selection (DB switch) | CompanySelectController | ◑ partial — top-bar DB switch works; the company registry (`storage/app/company-select.json`) + add/rename company UI not ported |
| **User Access editor** | UserAccessController | ✅ done (userm+userd, create→login round-trip tested) |
| **Application Settings** | ApplicationSettingsController | ✅ done — DB-backed part (shop info in `generals`, CLASTNO/SLASTNO, SBPREF/SBLEN). INI app/printer prefs + logo upload out of scope (file-based, not DB) |

## Phase 2 — Masters
| Module | Controller | Status |
|---|---|---|
| **Stock Type** | StockTypeController | ✅ done |
| **Item Group** | ItemGroupController | ✅ done |
| **Item Sub-Group** | ItemSubGroupController | ✅ done |
| **Item Purity Type** | ItemPurityTypeController | ✅ done (rename cascade + usage guard) |
| **Counters** | CountersController | ✅ done (generali seed) |
| **Bill Prefix** | BillPrefixController | ✅ done (salestype + counter seed; bulk stale-delete deferred) |
| **Denomination Master** | DenominationMasterController | ✅ done |
| **MC Table** | MCTableController | ✅ done (bulk slab replace) |
| Item Master | ItemMasterController | ⏳ remaining (largest master — read docs/item-create-logic.txt) |
| Party MC Table | PartyMCTableController | ⏳ remaining |
| Country/Currency (settings UI) | CountryCurrencyController | ◑ read at login; settings editor not ported |

## Recommended order to finish Phase 1 & 2
1. Application Settings (Phase 1) — small, writes `generals`.
2. Item Group + Item Sub-Group (Phase 2) — prerequisites for Item Master.
3. Item Master (Phase 2) — the big one; read `docs/item-create-logic.txt` first.
4. Counters, Bill Prefix, Denomination, MC Table — small masters, reuse the
   Stock Type pattern.
