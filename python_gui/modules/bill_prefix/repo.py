"""Bill Prefix repository — `salestype` + `generali` counters.

Source: BillPrefixController. salestype holds sales/sales-return/purchase/
purchase-return prefixes and start numbers; the live counters live in `generali`
under keys SALES<prefix>, SRET<srprefix>, PURCH<pprefix>, PRET<prprefix>.
resolveEffectiveCounter auto-heals the counter to max(generali, max bill no).
"""

from __future__ import annotations

import re

from ...core.db import Database, Tx

_SALESTYPE_COLS = ["code", "name", "taxperc", "formno", "prefix", "startno",
                   "srprefix", "srstartno", "pprefix", "pstartno", "prprefix", "prstartno"]


class BillPrefixRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, t: str) -> bool:
        return self.db.table_exists(t)

    def has_column(self, t: str, c: str) -> bool:
        return self.db.column_exists(t, c)

    def list_salestype(self) -> list[dict]:
        return self.db.fetchall(f"SELECT {', '.join(_SALESTYPE_COLS)} FROM salestype ORDER BY code")

    def generali_value(self, code: str, fallback: int = 0) -> int:
        v = self.db.scalar("SELECT cvalue FROM generali WHERE code = :c LIMIT 1", {"c": code})
        try:
            return int(v) if v is not None else int(fallback)
        except (TypeError, ValueError):
            return int(fallback)

    def upsert_generali(self, code: str, value: int, tx: Tx | None = None) -> None:
        runner = tx or self.db
        res = runner.execute("UPDATE generali SET cvalue = :v WHERE code = :c", {"v": value, "c": code})
        if getattr(res, "rowcount", 0) == 0:
            runner.execute("INSERT INTO generali (code, cvalue) VALUES (:c, :v)", {"c": code, "v": value})

    def max_billno_from(self, table: str, column: str, prefix: str) -> int:
        """Max numeric suffix among bill numbers starting with prefix (resolveEffectiveCounter)."""
        if prefix == "" or not self.has_table(table) or not self.has_column(table, column):
            return 0
        val = self.db.scalar(
            f"SELECT {column} FROM {table} WHERE {column} LIKE :p "
            f"ORDER BY LENGTH({column}) DESC, {column} DESC LIMIT 1",
            {"p": f"{prefix}%"},
        )
        if val is None:
            return 0
        suffix = str(val)[len(prefix):]
        digits = re.sub(r"[^0-9-]", "", suffix) or "0"
        try:
            return int(digits)
        except ValueError:
            return 0

    def resolve_effective_counter(self, gencode: str, prefix: str, table: str,
                                  column: str, fallback: int) -> int:
        gval = self.generali_value(gencode, fallback)
        if prefix == "" or not self.has_table(table) or not self.has_column(table, column):
            return gval
        effective = max(gval, self.max_billno_from(table, column, prefix))
        if effective > gval and self.has_table("generali") and gencode.strip() != "":
            self.upsert_generali(gencode, effective)
        return effective

    def upsert_salestype(self, tx: Tx, row: dict) -> None:
        res = tx.execute(
            "UPDATE salestype SET name=:name, taxperc=:taxperc, formno=:formno, prefix=:prefix, "
            "startno=:startno, srprefix=:srprefix, srstartno=:srstartno, pprefix=:pprefix, "
            "pstartno=:pstartno, prprefix=:prprefix, prstartno=:prstartno WHERE code=:code", row)
        if getattr(res, "rowcount", 0) == 0:
            cols = ", ".join(_SALESTYPE_COLS)
            binds = ", ".join(f":{c}" for c in _SALESTYPE_COLS)
            tx.execute(f"INSERT INTO salestype ({cols}) VALUES ({binds})", row)
