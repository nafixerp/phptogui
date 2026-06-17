"""Authentication, session and permissions.

Ports the legacy login flow. Sources:
  - app/Http/Controllers/NativeAuthController.php  (login/logout/session)
  - app/Models/UserM.php                           (authenticateLegacy, userd)
  - app/Enums/Permission.php                        (menu permission keys)
  - app/Http/Controllers/CountryCurrencyController.php::getConfig()

Key facts replicated:
  * Login is PASSWORD-ONLY. Match: UserM::authenticateLegacy() does
        SELECT code,name FROM userm WHERE UPPER(HEX(pcode)) = :hex
    where :hex = pcode_hex(password)  (see core.crypto, verified vs PHP).
  * After login the controller stores: user_code, user_name (trimmed),
    gsuserid/gsusername (= code/name), login_time, selected_database,
    show_startup_popups=true, blocked_items, readonly, currency_config.
  * blocked_items = userd.menuitem WHERE TRIM(code)=user_code  — these are the
    menu items the user is DENIED (NativeAuthController::login).
  * readonly = 'Y' if userd has a row with TRIM(menuitem)='READONLY'.
  * Login history inserted into userhist (code, tdate, time1, ip, useragent)
    only for columns that exist; logout stamps time2 on the open row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .crypto import pcode_hex
from .db import Database, db


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

@dataclass
class AppSession:
    user_code: str
    user_name: str
    selected_database: str
    blocked_items: set[str] = field(default_factory=set)
    readonly: bool = False
    currency_config: dict = field(default_factory=dict)
    login_time: datetime = field(default_factory=datetime.now)

    # Mirrors session('gsuserid'/'gsusername') used across Laravel controllers.
    @property
    def gsuserid(self) -> str:
        return self.user_code

    @property
    def gsusername(self) -> str:
        return self.user_name

    # Permission model: userd lists DENIED menu items (see NativeAuthController).
    def is_blocked(self, menuitem: str) -> bool:
        return menuitem.strip().upper() in self.blocked_items

    def can(self, menuitem: str) -> bool:
        """True if the user may access this MDI menu item."""
        if self.readonly and menuitem.strip().upper() == "READONLY":
            return True
        return not self.is_blocked(menuitem)


# ---------------------------------------------------------------------------
# Defaults (CountryCurrencyController::defaultConfig)
# ---------------------------------------------------------------------------

def default_currency_config() -> dict:
    # Mirrors CountryCurrencyController::defaultConfig() IN profile basics.
    return {
        "id": 1,
        "country_code": "IN",
        "base_currency": "INR",
        "currency_code": "INR",
        "currency_symbol": "₹",
        "currency_name": "Indian Rupee",
        "date_format": "DD/MM/YYYY",
        "decimal_places": 2,
        "weight_unit": "gram",
        "tax_label": "GST",
        "number_format": "indian",
    }


# ---------------------------------------------------------------------------
# Auth service
# ---------------------------------------------------------------------------

class AuthError(Exception):
    pass


class AuthService:
    def __init__(self, database: Database | None = None):
        self.db = database or db()

    # -- shop branding for the login screen (generals table) ---------------
    def shop_info(self) -> dict:
        info = {
            "name": "Proaims Custom Dashboard",
            "address": "",
            "phone": "",
            "gst": "",
        }
        try:
            def gv(code: str) -> str | None:
                row = self.db.fetchone(
                    "SELECT cvalue FROM generals WHERE code = :c LIMIT 1", {"c": code}
                )
                return (row or {}).get("cvalue")

            info["name"] = (gv("SHOPNM") or info["name"]).strip() or info["name"]
            info["address"] = (gv("SHOPADDR") or "").strip()
            info["phone"] = (gv("SHOPPHONE") or "").strip()
            info["gst"] = (gv("GSTIN") or gv("GSTNO") or "").strip()
        except Exception:
            pass  # DB not reachable yet — fall back to defaults
        return info

    @staticmethod
    def greeting(now: datetime | None = None) -> str:
        hour = (now or datetime.now()).hour
        if 5 <= hour < 12:
            return "Good Morning"
        if 12 <= hour < 17:
            return "Good Afternoon"
        if 17 <= hour < 22:
            return "Good Evening"
        return "Welcome"

    # -- core authentication ------------------------------------------------
    def authenticate(self, password: str) -> AppSession:
        """Validate a password and build the session. Raises AuthError on failure.

        Mirrors NativeAuthController::login + UserM::authenticateLegacy.
        """
        password = (password or "").strip()
        if password == "":
            raise AuthError("Please enter password")

        if not self.db.table_exists("userm"):
            raise AuthError(
                "Login table not found. Verify DB_DATABASE in .env and import the schema."
            )

        hexkey = pcode_hex(password)
        user = self.db.fetchone(
            "SELECT code, name FROM userm WHERE UPPER(HEX(pcode)) = :hex LIMIT 1",
            {"hex": hexkey},
        )
        if not user:
            raise AuthError("Invalid password")

        user_code = str(user.get("code") or "").strip()
        user_name = str(user.get("name") or "").strip()

        session = AppSession(
            user_code=user_code,
            user_name=user_name,
            selected_database=self.db.database,
        )
        session.blocked_items = self._load_blocked_items(user_code)
        session.readonly = "READONLY" in session.blocked_items
        session.currency_config = self._load_currency_config()

        self._record_login(session)
        return session

    def _load_blocked_items(self, user_code: str) -> set[str]:
        if not self.db.table_exists("userd"):
            return set()
        rows = self.db.fetchall(
            "SELECT menuitem FROM userd WHERE TRIM(code) = :c", {"c": user_code}
        )
        return {str(r["menuitem"]).strip().upper() for r in rows if r.get("menuitem") is not None}

    def _load_currency_config(self) -> dict:
        try:
            if self.db.table_exists("country_currency_config"):
                row = self.db.fetchone(
                    "SELECT * FROM country_currency_config WHERE id = 1 LIMIT 1"
                )
                if row:
                    return row
        except Exception:
            pass
        return default_currency_config()

    def _record_login(self, session: AppSession) -> None:
        """Insert a userhist row for the columns that exist (best effort)."""
        try:
            if not self.db.table_exists("userhist"):
                return
            cols: dict[str, object] = {"code": session.user_code}
            if self.db.column_exists("userhist", "tdate"):
                cols["tdate"] = date.today().isoformat()
            if self.db.column_exists("userhist", "time1"):
                cols["time1"] = datetime.now().strftime("%H:%M:%S")
            if self.db.column_exists("userhist", "ip"):
                cols["ip"] = "127.0.0.1"
            if self.db.column_exists("userhist", "useragent"):
                cols["useragent"] = "GoldApp-Desktop"
            names = ", ".join(cols.keys())
            binds = ", ".join(f":{k}" for k in cols)
            self.db.execute(f"INSERT INTO userhist ({names}) VALUES ({binds})", cols)
        except Exception:
            pass  # history is non-critical; never block login on it

    def record_logout(self, session: AppSession) -> None:
        """Stamp time2 on the most recent open userhist row (NativeAuthController::logout)."""
        try:
            if not self.db.table_exists("userhist"):
                return
            today = date.today().isoformat()
            row = self.db.fetchone(
                "SELECT time1 FROM userhist "
                "WHERE TRIM(code) = :c AND tdate = :d AND (time2 IS NULL OR time2 = '') "
                "ORDER BY time1 DESC LIMIT 1",
                {"c": session.user_code, "d": today},
            )
            if row and row.get("time1") is not None:
                self.db.execute(
                    "UPDATE userhist SET time2 = :t2 "
                    "WHERE TRIM(code) = :c AND tdate = :d AND time1 = :t1",
                    {
                        "t2": datetime.now().strftime("%H:%M:%S"),
                        "c": session.user_code,
                        "d": today,
                        "t1": row["time1"],
                    },
                )
        except Exception:
            pass
