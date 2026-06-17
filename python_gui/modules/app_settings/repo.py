"""Application Settings repository — DB-backed values in `generals` / `generali`.

Source: ApplicationSettingsController (load / persistShopInfo /
persistGeneraliCounter / persistGeneralsValue). Shop name/address/phone live in
`generals` (SHOPNM/SHOPADDR/SHOPPHONE); CLASTNO/SLASTNO in `generali`;
SBPREF/SBLEN in `generals`. (The INI-file app/printer prefs are not DB-backed.)
"""

from __future__ import annotations

from ...core.db import Database


class AppSettingsRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_generals(self) -> bool:
        return self.db.table_exists("generals")

    def generals_value(self, code: str, default: str = "") -> str:
        if not self.has_generals():
            return default
        v = self.db.scalar("SELECT cvalue FROM generals WHERE code = :c LIMIT 1", {"c": code})
        return default if v is None else str(v)

    def generali_value(self, code: str, default: str = "0") -> str:
        v = self.db.scalar("SELECT cvalue FROM generali WHERE code = :c LIMIT 1", {"c": code})
        if v is None:
            return default
        try:
            return str(int(v))
        except (TypeError, ValueError):
            return str(v)

    def set_generals(self, tx, code: str, value: str) -> None:
        if not self.has_generals():
            return
        res = tx.execute("UPDATE generals SET cvalue = :v WHERE code = :c", {"v": value, "c": code})
        if getattr(res, "rowcount", 0) == 0:
            tx.execute("INSERT INTO generals (code, cvalue) VALUES (:c, :v)", {"c": code, "v": value})

    def set_generali(self, tx, code: str, value: int) -> None:
        res = tx.execute("UPDATE generali SET cvalue = :v WHERE code = :c", {"v": value, "c": code})
        if getattr(res, "rowcount", 0) == 0:
            tx.execute("INSERT INTO generali (code, cvalue) VALUES (:c, :v)", {"c": code, "v": value})
