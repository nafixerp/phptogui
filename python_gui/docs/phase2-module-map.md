# Phase 2 — Masters — Module Map

Laravel controller / view / table for each Phase 2 master, with the exact rules
to port. Built one module at a time. **Stock Type is done** and establishes the
`repo.py` / `service.py` / `view.py` pattern + reusable `DataGrid` widget +
`core/audit.py` (delpart logging) that the rest will reuse.

| Module | Controller | View | Tables | Notes |
|---|---|---|---|---|
| **Stock Type** ✅ | `StockTypeController` | `stocktype/index` | `stktype` (+ usage: `itemsstk`, `salesd`, `salesrd`, `purchased`, `purchaserd`, `smithd`, `refineryd`, `repaird`, `itemadj`) | full CRUD + usage-guarded delete |
| Item Group | `ItemGroupController` | `groups` | `groups` | code/name master |
| Item Sub-Group | `ItemSubGroupController` | `sub-groups` | `subgroups` | linked to group |
| Item Purity Type | `ItemPurityTypeController` | `purity-type` | purity table | check-delete |
| Counters | `CountersController` | `counters` | `counters` | save/delete |
| Bill Prefix | `BillPrefixController` | `bill-prefix` | bill-prefix table | retrieve/save/check-delete |
| Denomination Master | `DenominationMasterController` | `denomination-master` | `denom_master` | retrieve/save/check-ref |
| MC Table | `MCTableController` | `mctable` | `mctable` | weight-slab making-charge lookup |
| Party MC Table | `PartyMCTableController` | `partymctable` | party MC table | party-specific MC |
| Stock Type module settings | `StockTypeController::moduleSettings` | `stocktype/module-settings` | — | settings page |
| Country/Currency | `CountryCurrencyController` | `country-currency/index` | `country_currency_config` | already read at login (core.auth) |

## Stock Type — extracted rules (parity reference)

Source: `app/Http/Controllers/StockTypeController.php`,
`app/Models/StockType.php`, `app/Http/Requests/StoreStockTypeRequest.php`.
Frozen schema (`complete_database_export.sql:2514`):
`stktype(code CHAR(5) PK, name VARCHAR(20), def SMALLINT, compare SMALLINT)`.

- **Validation:** code required, ≤10, unique, UPPER+TRIM; name required, ≤30,
  TRIM; def/compare → 1/0.
- **store:** INSERT then, if default, `setAsDefault` — atomic (one transaction).
- **update:** UPDATE name/def/compare by code, then optional `setAsDefault` —
  atomic.
- **setAsDefault:** keep a single default. **Deviation (documented):** the
  Eloquent model clears other defaults by `id`, but the production `demo` table
  has **no `id` column** (code is the PK), so the PHP path would raise
  *"Unknown column 'id'"*. The port keys this on `code`, which is correct for
  both the legacy schema and the migration-created schema. → confirm with the
  team whether any live DB actually has the `id` column.
- **destroy decision tree:**
  - `usage.total == 0` → delete.
  - `total>0 and total==itemsonly` → confirm-required (deletable with items via
    force; `deleteWithItems` also removes matching `itemsstk` rows).
  - `total>0 and total!=itemsonly` → blocked (referenced by transactions).
  - force → `deleteWithItems`.
- **isInUse:** column-guarded COUNTs; `itemsstk` only counts rows with non-zero
  `qty/qtyb/weight/weightb`.
- **audit:** add/edit/delete log a `delpart` row (utype A/E/D, ttype R) via
  `LogsDelpartAudit`.

## Parity status (Stock Type)

- Service decision-tree + validation: unit-tested headless (`tests/test_stocktype_service.py`).
- Repo SQL (INSERT/UPDATE/DELETE/SELECT) + single-default invariant + atomic
  delete: executed against a real SQL engine and verified.
- Live `demo` row-count before/after proof: pending a machine with MySQL (the
  build sandbox has none). Run with XAMPP up:
  `python -m python_gui.main` → Stock Type → add/edit/delete, then compare
  `SELECT * FROM stktype` against the Laravel app.
