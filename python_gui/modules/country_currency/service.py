"""Country / Currency / Religion settings editor — `country_currency_config`.

Source: CountryCurrencyController (getConfig/save). Reads the single config row
(id=1); writes when the table exists (it is app-created — guarded). Falls back to
the India default profile (mirrors defaultConfig()).
"""

from __future__ import annotations

from ...core.auth import AppSession
from ...core.auth import default_currency_config
from ...core.db import Database
from ...core.decimals import to_decimal

_FIELDS = ["country_code", "country_name", "religion", "currency_code", "currency_symbol",
           "currency_name", "base_currency", "date_format", "calendar_type", "weight_unit",
           "purity_system", "tax_label", "number_format", "working_days"]


class CountryCurrencyService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def available(self) -> bool:
        return self.db.table_exists("country_currency_config")

    def load(self) -> dict:
        if self.available():
            row = self.db.fetchone("SELECT * FROM country_currency_config WHERE id = 1 LIMIT 1")
            if row:
                return row
        return default_currency_config()

    def save(self, data: dict) -> str:
        if not self.available():
            raise RuntimeError("country_currency_config table not found")
        row = {f: str(data.get(f) or "").strip() for f in _FIELDS}
        row["exchange_rate"] = max(0.000001, float(to_decimal(data.get("exchange_rate", 1)) or 1))
        row["decimal_places"] = min(4, max(0, int(to_decimal(data.get("decimal_places", 2)) or 0)))
        row["rtl"] = 1 if data.get("rtl") else 0
        with self.db.transaction() as tx:
            exists = tx.scalar("SELECT 1 FROM country_currency_config WHERE id = 1 LIMIT 1") is not None
            if exists:
                sets = ", ".join(f"{k} = :{k}" for k in row)
                tx.execute(f"UPDATE country_currency_config SET {sets} WHERE id = 1", row)
            else:
                cols = ", ".join(["id", *row]); binds = ", ".join([":id", *(f":{k}" for k in row)])
                tx.execute(f"INSERT INTO country_currency_config ({cols}) VALUES ({binds})", {"id": 1, **row})
        return "Country/Currency settings saved"
