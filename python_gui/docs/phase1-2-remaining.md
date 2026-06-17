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
| **User Access editor** | UserAccessController | ✅ **done** (userm+userd, create→login round-trip tested) |
| Application Settings | ApplicationSettingsController | ⏳ remaining (shop name/logo/general flags in `generals`) |

## Phase 2 — Masters
| Module | Controller | Status |
|---|---|---|
| **Stock Type** | StockTypeController | ✅ done |
| Item Master | ItemMasterController | ⏳ remaining (largest master) |
| Item Group | ItemGroupController | ⏳ remaining |
| Item Sub-Group | ItemSubGroupController | ⏳ remaining |
| Item Purity Type | ItemPurityTypeController | ⏳ remaining |
| Counters | CountersController | ⏳ remaining |
| Bill Prefix | BillPrefixController | ⏳ remaining |
| Denomination Master | DenominationMasterController | ⏳ remaining |
| MC Table | MCTableController | ⏳ remaining |
| Party MC Table | PartyMCTableController | ⏳ remaining |
| Country/Currency (settings UI) | CountryCurrencyController | ◑ read at login; settings editor not ported |

## Recommended order to finish Phase 1 & 2
1. Application Settings (Phase 1) — small, writes `generals`.
2. Item Group + Item Sub-Group (Phase 2) — prerequisites for Item Master.
3. Item Master (Phase 2) — the big one; read `docs/item-create-logic.txt` first.
4. Counters, Bill Prefix, Denomination, MC Table — small masters, reuse the
   Stock Type pattern.
