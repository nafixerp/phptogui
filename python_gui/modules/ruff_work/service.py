"""Ruff Work memo — port of RuffWorkController (list / bulk-save / delete).

A free-form rough-work memo grid in `ruffwrk`. ``save`` upserts each row by
``slno`` (a blank party deletes an existing row, or skips a new one),
column-filtered to the live schema.
"""

from __future__ import annotations

from datetime import date

from ...core.db import Database

_FIELDS = ["party", "tdate", "item", "qty", "weight", "amount", "part",
           "inexp", "sman", "person", "pend", "number"]


class RuffWorkService:
    def __init__(self, database: Database, control: int = 1):
        self.db = database
        self.control = int(control or 1)

    def list(self, party: str = "") -> list[dict]:
        if not self.db.table_exists("ruffwrk"):
            return []
        where = ["1=1"]
        params: dict = {}
        if party.strip():
            where.append("UPPER(TRIM(party)) = :p"); params["p"] = party.strip().upper()
        return self.db.fetchall(
            f"SELECT * FROM ruffwrk WHERE {' AND '.join(where)} ORDER BY tdate DESC, slno DESC LIMIT 5000", params)

    def save(self, rows: list[dict]) -> str:
        if not self.db.table_exists("ruffwrk"):
            raise RuntimeError("ruffwrk table not found")
        cols = set(self.db.columns("ruffwrk"))
        with self.db.transaction() as tx:
            for row in rows:
                slno = int(row.get("slno") or 0)
                party = str(row.get("party") or "").strip()
                if party == "" and slno > 0:
                    tx.execute("DELETE FROM ruffwrk WHERE slno = :s", {"s": slno})
                    continue
                if party == "":
                    continue
                data = {
                    "party": party, "tdate": str(row.get("tdate") or "").strip() or date.today().isoformat(),
                    "item": str(row.get("item") or "").strip()[:30], "qty": str(row.get("qty") or "").strip()[:20],
                    "weight": str(row.get("weight") or "").strip()[:20], "amount": str(row.get("amount") or "").strip()[:30],
                    "part": str(row.get("part") or "").strip()[:30], "inexp": str(row.get("inexp") or "").strip()[:3],
                    "sman": str(row.get("sman") or "").strip()[:30], "person": str(row.get("person") or "").strip()[:30],
                    "pend": int(row.get("pend") if row.get("pend") not in (None, "") else 1),
                    "number": int(row.get("number") or 0), "control": self.control,
                }
                use = {k: v for k, v in data.items() if k in cols}
                exists = slno > 0 and tx.fetchall("SELECT 1 FROM ruffwrk WHERE slno = :s LIMIT 1", {"s": slno})
                if exists:
                    sets = ", ".join(f"{k} = :{k}" for k in use)
                    tx.execute(f"UPDATE ruffwrk SET {sets} WHERE slno = :slno", {**use, "slno": slno})
                else:
                    names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
                    tx.execute(f"INSERT INTO ruffwrk ({names}) VALUES ({binds})", use)
        return "Saved successfully"

    def delete(self, slno: int) -> str:
        slno = int(slno)
        if slno <= 0 or not self.db.table_exists("ruffwrk"):
            raise RuntimeError("Record not found")
        self.db.execute("DELETE FROM ruffwrk WHERE slno = :s", {"s": slno})
        return "Row deleted"
