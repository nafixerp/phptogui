"""Wastage Table — `wstgtable(code, weight1, weight2, wastage, perc, iqtype)`.

Source: WastageTableController. Weight-slab wastage per (code, iqtype); a save
deletes existing slabs for that pair and reinserts (entries with weight1==0 and
weight2==0 are skipped). Same shape as the MC Table.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import to_decimal


class WastageError(Exception):
    pass


class WastageTableService:
    _NUM = ["weight1", "weight2", "wastage", "perc"]

    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def get_for_item(self, code: str, iqtype: str = "") -> list[dict]:
        if not self.db.table_exists("wstgtable"):
            return []
        return self.db.fetchall(
            "SELECT weight1, weight2, wastage, perc FROM wstgtable "
            "WHERE UPPER(TRIM(code)) = :c AND iqtype = :q ORDER BY weight1",
            {"c": code.strip().upper(), "q": iqtype.strip()},
        )

    def save(self, code: str, iqtype: str, entries: list[dict]) -> str:
        code = str(code or "").strip().upper()
        if code == "":
            raise WastageError("Item code is required")
        iqtype = str(iqtype or "").strip()
        n = 0
        with self.db.transaction() as tx:
            sql = "DELETE FROM wstgtable WHERE UPPER(TRIM(code)) = :c" + (" AND iqtype = :q" if iqtype else "")
            tx.execute(sql, {"c": code, "q": iqtype} if iqtype else {"c": code})
            for e in entries:
                w1 = to_decimal(e.get("weight1", 0)) or Decimal("0")
                w2 = to_decimal(e.get("weight2", 0)) or Decimal("0")
                if w1 == 0 and w2 == 0:
                    continue
                row = {"code": code, "iqtype": iqtype, "weight1": w1, "weight2": w2,
                       "wastage": to_decimal(e.get("wastage", 0)) or Decimal("0"),
                       "perc": to_decimal(e.get("perc", 0)) or Decimal("0")}
                cols = ", ".join(row); binds = ", ".join(f":{k}" for k in row)
                tx.execute(f"INSERT INTO wstgtable ({cols}) VALUES ({binds})", row)
                n += 1
        log_delpart(self.db, self.session, f"Wastage({code}{'/' + iqtype if iqtype else ''}) Saved",
                    utype="E", ttype="R")
        return f"Updated ({n} slab(s))."
