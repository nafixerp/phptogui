"""MC Table repository — `mctable` weight-slab making charges.

Source: MCTableController + MCTable::bulkUpdateForItem. Rows are keyed by
(code, iqtype); a save replaces all slabs for that pair. Entries with
weight1==0 and weight2==0 are skipped.
"""

from __future__ import annotations

from ...core.db import Database

_ENTRY_COLS = ["weight1", "weight2", "mc", "mcpergm", "mcperqty", "vaperc"]


class MCTableRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, t: str = "mctable") -> bool:
        return self.db.table_exists(t)

    def get_for_item(self, code: str, iqtype: str) -> list[dict]:
        return self.db.fetchall(
            "SELECT weight1, weight2, mc, mcpergm, mcperqty, vaperc FROM mctable "
            "WHERE UPPER(TRIM(code)) = :c AND iqtype = :q ORDER BY weight1",
            {"c": code.strip().upper(), "q": iqtype.strip()},
        )

    def item_types(self, code: str) -> list[str]:
        rows = self.db.fetchall(
            "SELECT DISTINCT iqtype FROM mctable WHERE UPPER(TRIM(code)) = :c", {"c": code.strip().upper()}
        )
        return [str(r["iqtype"] or "").strip() for r in rows]

    def bulk_update(self, code: str, iqtype: str, entries: list[dict]) -> int:
        """Port of MCTable::bulkUpdateForItem — delete (code,iqtype) then insert."""
        code = code.strip().upper()
        iqtype = iqtype.strip()
        inserted = 0
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM mctable WHERE UPPER(TRIM(code)) = :c AND iqtype = :q",
                       {"c": code, "q": iqtype})
            for e in entries:
                w1 = e.get("weight1") or 0
                w2 = e.get("weight2") or 0
                if float(w1) == 0.0 and float(w2) == 0.0:
                    continue
                row = {"code": code, "iqtype": iqtype, "weight1": w1, "weight2": w2,
                       "mc": e.get("mc") or 0, "mcpergm": e.get("mcpergm") or 0,
                       "mcperqty": e.get("mcperqty") or 0, "vaperc": e.get("vaperc") or 0}
                cols = ", ".join(row)
                binds = ", ".join(f":{k}" for k in row)
                tx.execute(f"INSERT INTO mctable ({cols}) VALUES ({binds})", row)
                inserted += 1
        return inserted
