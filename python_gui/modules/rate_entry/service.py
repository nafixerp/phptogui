"""Daily Rate entry — port of RateController.

Holds the current metal rates in ``generald`` (one row per code, value in
``cvalue``) and snapshots them into ``ratehistory`` once per day (upsert on
``tdate``). The ``RATESETUP`` permission gates saving. Decimal rounding per
code matches the legacy precision map.

Source: RateController::save / saveRate / saveRateHistory.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import quantize, to_decimal

# code -> decimal places (from RateController::$rateCodes)
RATE_CODES = {
    "BULRATE": 2, "BULTOUCH": 3, "GRATE": 2, "G18RATE": 2, "G14RATE": 2,
    "G9RATE": 2, "G4RATE": 2, "OGRATE": 2, "THRATE": 3, "PRATE": 2,
    "SRATE": 2, "JRATE": 2, "OSRATE": 2,
}
# ratehistory columns mapped from rate codes (lower-cased code = column)
_HISTORY = ["grate", "g18rate", "g14rate", "g9rate", "g4rate", "srate", "thrate",
            "prate", "bulrate", "bultouch", "jrate", "ograte", "osrate"]


class RateError(Exception):
    pass


class RateService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def can_edit(self) -> bool:
        if self.session is None:
            return True
        code = getattr(self.session, "user_code", "")
        if str(code) == "admin":
            return True
        is_blocked = getattr(self.session, "is_blocked", None)
        return not (callable(is_blocked) and is_blocked("RATESETUP"))

    def current(self) -> dict:
        rates = {}
        if self.db.table_exists("generald"):
            for code in RATE_CODES:
                v = self.db.scalar("SELECT cvalue FROM generald WHERE code = :c", {"c": code})
                rates[code] = to_decimal(v) or Decimal("0")
        else:
            rates = {c: Decimal("0") for c in RATE_CODES}
        return rates

    def save(self, values: dict) -> str:
        if not self.can_edit():
            raise RateError("You do not have permission to update rates")
        if not self.db.table_exists("generald"):
            raise RateError("generald table not found")
        rounded: dict[str, Decimal] = {}
        with self.db.transaction() as tx:
            for code, places in RATE_CODES.items():
                q = Decimal(10) ** -places
                val = quantize(values.get(code, values.get(code.lower(), 0)), q)
                rounded[code] = val
                exists = tx.fetchall("SELECT 1 FROM generald WHERE code = :c LIMIT 1", {"c": code})
                if exists:
                    tx.execute("UPDATE generald SET cvalue = :v WHERE code = :c", {"v": val, "c": code})
                else:
                    tx.execute("INSERT INTO generald (code, cvalue) VALUES (:c, :v)", {"c": code, "v": val})
            self._save_history(tx, rounded)
        return f"Rates saved successfully! Updated at {datetime.now().strftime('%I:%M %p')}"

    def _save_history(self, tx, rates: dict) -> None:
        if not self.db.table_exists("ratehistory"):
            return
        cols = set(self.db.columns("ratehistory"))
        today = date.today().isoformat()
        data = {"ttime": datetime.now().strftime("%H:%M:%S")}
        for col in _HISTORY:
            if col in cols:
                data[col] = rates.get(col.upper(), Decimal("0"))
        exists = tx.fetchall("SELECT 1 FROM ratehistory WHERE tdate = :t LIMIT 1", {"t": today})
        if exists:
            sets = ", ".join(f"{k} = :{k}" for k in data)
            tx.execute(f"UPDATE ratehistory SET {sets} WHERE tdate = :tdate", {**data, "tdate": today})
        else:
            data["tdate"] = today
            names = ", ".join(data); binds = ", ".join(f":{k}" for k in data)
            tx.execute(f"INSERT INTO ratehistory ({names}) VALUES ({binds})", data)
