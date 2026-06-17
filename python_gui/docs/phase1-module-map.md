# Phase 1 — Shell — Module Map

Laravel controllers / views / tables involved in Phase 1, with the exact rules
extracted (HARD RULE 2: rules quoted from source `file:line`).

## 1. `.env` / DB connection
- **Source:** `config/database.php` (mysql connection), `.env`
- **Facts:** driver `mysql`, host `127.0.0.1:3306`, database `demo`, user `root`,
  empty password, charset `utf8mb4`, collation `utf8mb4_unicode_ci`. Secondary
  company DB `deom12` from `DB_SECONDARY_DATABASE` / `SECONDARY_DATABASE`.
- **Ported to:** `core/config.py`, `core/db.py`

## 2. Legacy login  ✅ parity-proven
- **Source:** `app/Http/Controllers/NativeAuthController.php`,
  `app/Models/UserM.php`, `app/Services/PasswordService.php`
- **Rules:**
  - Login is **password only**. Match query (`UserM::authenticateLegacy`,
    UserM.php:23-32):
    `SELECT code,name FROM userm WHERE UPPER(HEX(pcode)) = ?` where the bind is
    `strtoupper(bin2hex(fpencrypt(password)))`.
  - `fpCrypt` (UserM.php:76-96): byte-wise; for byte `i` of the trimmed string
    `offset=(i+1)*(len+2)`, `out=(byte+offset)%256`; prepend a space, PHP-`trim`
    the raw bytes, then `mb_convert_encoding(..,'UTF-8','Windows-1252')`.
  - On success the controller stores session keys (NativeAuthController.php:79-99):
    `user_code`, `user_name` (both trimmed), `gsuserid`, `gsusername`,
    `login_time`, `selected_database`, `show_startup_popups=true`.
  - `blocked_items` = `userd.menuitem WHERE TRIM(code)=user_code`
    (NativeAuthController.php:101-110) — these are **denied** menu items.
  - `readonly` = `'Y'` if `userd` has `TRIM(menuitem)='READONLY'`
    (NativeAuthController.php:112-119).
  - `currency_config` from `CountryCurrencyController::getConfig()`
    (`country_currency_config` id=1, else `defaultConfig()`).
  - `userhist` insert of `code/tdate/time1/ip/useragent` for existing columns
    (NativeAuthController.php:123-138); logout stamps `time2`
    (NativeAuthController.php:140-167).
- **Ported to:** `core/crypto.py`, `core/auth.py`

## 3. Permissions
- **Source:** `app/Enums/Permission.php` (`grouped()`, `mdiMenus()`),
  table `userd`
- **Rules:** menu structure = `Permission::grouped()`; a user is denied a key if
  it is in `userd` for their code. `READONLY` is both a flag and a permission key.
- **Ported to:** `core/permissions.py`, enforced in `ui/shell.py` via
  `AppSession.can()`.

## 4. Dashboard + sidebar shell
- **Source:** `NativeDashboardController`, `resources/views/native/login.blade.php`
- **Ported to:** `ui/shell.py` (sidebar from allowed permissions, company
  selector, dashboard summary), `ui/login.py`.

## 5. Company selection
- **Source:** `CompanySelectController` (+ NativeAuthController
  `applySelectedDatabaseContext` / `resolveSelectedDatabase`)
- **Rule:** switching company re-points the mysql connection to another database
  name on the same server (`Config::set(... .database) + DB::purge + DB::reconnect`).
- **Ported to:** `core/db.py::Database.use_database`, `ui/shell.py` company menu.

## Remaining Phase 1 windows (next, one at a time)
- `ApplicationSettingsController` → application settings window
- `UserAccessController` → user access / permission editor (writes `userd`)
- `AdministrationController` / `BackupController` → admin + backup
