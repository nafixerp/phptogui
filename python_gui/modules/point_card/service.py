"""Point Card — `pcardtable(pcard, isubgrp, pointbasedon, valuefor1point,
valueperpoint, minsalesamt, rounddown)`. Source: PointCardController.

Per-row upsert keyed on (pcard, isubgrp).
"""

from __future__ import annotations

from decimal import Decimal

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import to_decimal

_NUM = ["valuefor1point", "valueperpoint", "minsalesamt"]


class PointCardError(Exception):
    pass


class PointCardService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def list(self) -> list[dict]:
        if not self.db.table_exists("pcardtable"):
            return []
        return self.db.fetchall(
            "SELECT pcard, isubgrp, pointbasedon, valuefor1point, valueperpoint, "
            "minsalesamt, rounddown FROM pcardtable ORDER BY pcard, isubgrp")

    def save(self, data: dict) -> str:
        pcard = str(data.get("pcard") or "").strip().upper()
        isubgrp = str(data.get("isubgrp") or "").strip().upper()
        if pcard == "":
            raise PointCardError("Point card code is required")
        row = {"pcard": pcard, "isubgrp": isubgrp,
               "pointbasedon": str(data.get("pointbasedon") or "").strip(),
               "rounddown": str(data.get("rounddown") or "N").strip().upper()[:1] or "N"}
        for k in _NUM:
            row[k] = to_decimal(data.get(k, 0)) or Decimal("0")
        with self.db.transaction() as tx:
            exists = tx.scalar(
                "SELECT 1 FROM pcardtable WHERE UPPER(TRIM(pcard)) = :p AND UPPER(TRIM(isubgrp)) = :g LIMIT 1",
                {"p": pcard, "g": isubgrp}) is not None
            if exists:
                upd = {k: v for k, v in row.items() if k not in ("pcard", "isubgrp")}
                sets = ", ".join(f"{k} = :{k}" for k in upd)
                upd.update({"_p": pcard, "_g": isubgrp})
                tx.execute(f"UPDATE pcardtable SET {sets} WHERE UPPER(TRIM(pcard)) = :_p AND UPPER(TRIM(isubgrp)) = :_g", upd)
            else:
                cols = ", ".join(row); binds = ", ".join(f":{k}" for k in row)
                tx.execute(f"INSERT INTO pcardtable ({cols}) VALUES ({binds})", row)
        return "Saved."

    def delete(self, pcard: str, isubgrp: str = "") -> str:
        self.db.execute("DELETE FROM pcardtable WHERE UPPER(TRIM(pcard)) = :p AND UPPER(TRIM(isubgrp)) = :g",
                        {"p": pcard.strip().upper(), "g": isubgrp.strip().upper()})
        return "Deleted."
