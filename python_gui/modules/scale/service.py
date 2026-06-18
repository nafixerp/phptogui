"""Scale Settings — key/value settings stored in `generals`.

Source: ScaleController::saveSettings (upsert generals). Reads and writes the
weighing-scale config keys.
"""

from __future__ import annotations

from ...core.auth import AppSession
from ...core.db import Database

# common scale setting keys (extend as needed)
SCALE_KEYS = ["SCALEPORT", "SCALEBAUD", "SCALEPREFIX", "SCALESUFFIX", "SCALEWGTDIGITS", "SCALEMODE"]


class ScaleService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def load(self, keys: list[str] | None = None) -> dict:
        out = {}
        if not self.db.table_exists("generals"):
            return {k: "" for k in (keys or SCALE_KEYS)}
        for k in (keys or SCALE_KEYS):
            v = self.db.scalar("SELECT cvalue FROM generals WHERE code = :c LIMIT 1", {"c": k})
            out[k] = "" if v is None else str(v)
        return out

    def save(self, settings: dict) -> str:
        if not self.db.table_exists("generals"):
            raise RuntimeError("generals table not found")
        with self.db.transaction() as tx:
            for code, value in settings.items():
                val = str(value or "")
                res = tx.execute("UPDATE generals SET cvalue = :v WHERE code = :c", {"v": val, "c": code})
                if getattr(res, "rowcount", 0) == 0:
                    tx.execute("INSERT INTO generals (code, cvalue) VALUES (:c, :v)", {"c": code, "v": val})
        return "Scale settings saved"
