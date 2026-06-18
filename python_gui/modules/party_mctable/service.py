"""Party MC Table — `pmctable(pcode, icode, model, submodel, wastage, mc,
mcperc, mcperqty, touch, formula)`. Source: PartyMCTableController +
PartyMCTable::bulkUpdateForParty. Bulk-replace all MC override rows for a party.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import to_decimal

_NUM = ["wastage", "mc", "mcperc", "mcperqty", "touch"]
_TXT = ["icode", "model", "submodel", "formula"]


class PartyMCError(Exception):
    pass


class PartyMCTableService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def get_for_party(self, pcode: str) -> list[dict]:
        if not self.db.table_exists("pmctable"):
            return []
        return self.db.fetchall(
            "SELECT pcode, icode, model, submodel, wastage, mc, mcperc, mcperqty, touch, formula "
            "FROM pmctable WHERE UPPER(TRIM(pcode)) = :p ORDER BY icode",
            {"p": pcode.strip().upper()})

    def save(self, pcode: str, entries: list[dict]) -> str:
        pcode = str(pcode or "").strip().upper()
        if pcode == "":
            raise PartyMCError("Party code is required")
        if not self.db.table_exists("pmctable"):
            raise PartyMCError("pmctable not found")
        n = 0
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM pmctable WHERE UPPER(TRIM(pcode)) = :p", {"p": pcode})
            for e in entries:
                row = {"pcode": pcode}
                for k in _TXT:
                    row[k] = str(e.get(k) or "").strip()
                for k in _NUM:
                    row[k] = to_decimal(e.get(k, 0)) or Decimal("0")
                if row["icode"] == "" and row["model"] == "":
                    continue
                cols = ", ".join(row); binds = ", ".join(f":{k}" for k in row)
                tx.execute(f"INSERT INTO pmctable ({cols}) VALUES ({binds})", row)
                n += 1
        log_delpart(self.db, self.session, f"Party MC Table({pcode}) Updated", utype="E", ttype="R")
        return f"MC Table updated successfully ({n} row(s))."
