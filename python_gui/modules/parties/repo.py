"""Parties repository — SQL against the frozen `clients` / `accountm` tables.

Source: app/Http/Controllers/NativeCustomerController.php.
Frozen schema: `clients(code CHAR(8) PK, name, ctype CHAR(1), opbalance, ...)`
(complete_database_export.sql:276) and `AccountM(accode CHAR(8) PK, ...)` (:37).

A single `clients` row stores every party type via `ctype`:
C=Customer S=Supplier F=Staff D=Depositor(ctype=C,grp=DEP) G=Goldsmith
R=Refiner J=Jewellery. The matching account row is `accountm.accode = code`.

Code generation uses `generali` (CLASTNO/SLASTNO numeric counters) and
`generals` (CPREFIX/SPREFIX text). All writes are column-filtered to the actual
table schema, mirroring the controller's array_filter(schemaTableColumns).
"""

from __future__ import annotations

import re

from ...core.db import Database, Tx


class PartiesRepo:
    def __init__(self, database: Database):
        self.db = database

    # -- schema helpers -----------------------------------------------------
    def has_table(self, table: str) -> bool:
        return self.db.table_exists(table)

    def columns(self, table: str) -> set[str]:
        return set(self.db.columns(table))

    def filter_columns(self, table: str, row: dict) -> dict:
        cols = self.columns(table)
        return {k: v for k, v in row.items() if k.lower() in cols}

    # -- reads --------------------------------------------------------------
    def client_exists(self, code: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM clients WHERE code = :c LIMIT 1", {"c": code}
        ) is not None

    def get_client(self, code: str) -> dict | None:
        return self.db.fetchone(
            'SELECT * FROM clients WHERE TRIM(COALESCE(code, "")) = :c LIMIT 1',
            {"c": code.strip()},
        )

    def get_accountm(self, code: str) -> dict | None:
        if not self.has_table("accountm"):
            return None
        return self.db.fetchone(
            'SELECT * FROM accountm WHERE TRIM(COALESCE(accode, "")) = :c LIMIT 1',
            {"c": code.strip()},
        )

    def get_advanced(self, code: str) -> dict | None:
        if not self.has_table("clients_advanced"):
            return None
        return self.db.fetchone(
            'SELECT * FROM clients_advanced WHERE TRIM(COALESCE(code, "")) = :c LIMIT 1',
            {"c": code.strip()},
        )

    def list_by_type(self, ctype: str, search: str, no_removed: bool) -> list[dict]:
        """Port of queryCustomersByType()."""
        sql = (
            "SELECT code, name, mobile, telephone, city, addr1, ctype, grp, removed "
            "FROM clients WHERE "
        )
        params: dict = {}
        if ctype == "D":
            cond = "ctype = 'C' AND (LEFT(COALESCE(grp,''),3) = 'DEP'"
            if "dcount" in self.columns("clients"):
                cond += " OR dcount > 0"
            cond += ")"
            sql += cond
        else:
            sql += "ctype = :t"
            params["t"] = ctype

        if no_removed and "removed" in self.columns("clients"):
            sql += " AND (removed <> 1 OR removed IS NULL)"

        if search:
            params["s"] = f"%{search}%"
            sql += (" AND (code LIKE :s OR name LIKE :s OR mobile LIKE :s "
                    "OR telephone LIKE :s OR city LIKE :s OR addr1 LIKE :s)")

        sql += " ORDER BY name LIMIT 300"
        return self.db.fetchall(sql, params)

    # -- code generation ----------------------------------------------------
    def generali_value(self, code: str) -> int:
        val = self.db.scalar("SELECT cvalue FROM generali WHERE code = :c LIMIT 1", {"c": code})
        try:
            return int(val) if val is not None else 0
        except (TypeError, ValueError):
            return 0

    def generals_value(self, code: str) -> str | None:
        val = self.db.scalar("SELECT cvalue FROM generals WHERE code = :c LIMIT 1", {"c": code})
        return None if val is None else str(val)

    def set_generali(self, code: str, value: int, tx: Tx | None = None) -> None:
        # Laravel updateOrInsert(['code'=>..],['cvalue'=>..])
        runner = tx or self.db
        affected = runner.execute(
            "UPDATE generali SET cvalue = :v WHERE code = :c", {"v": value, "c": code}
        )
        if getattr(affected, "rowcount", 0) == 0:
            runner.execute(
                "INSERT INTO generali (code, cvalue) VALUES (:c, :v)", {"c": code, "v": value}
            )

    def max_party_code_number(self, prefix: str) -> int:
        """Port of getMaxPartyCodeNumber(): max numeric suffix of PREFIX<digits>."""
        prefix = prefix.strip().upper()
        if prefix == "":
            return 0
        # MySQL REGEXP mirrors the PHP query; we re-parse in Python for the max.
        rows = self.db.fetchall(
            "SELECT code FROM clients WHERE code REGEXP :rx",
            {"rx": "^" + re.escape(prefix) + "[0-9]+$"},
        )
        pat = re.compile("^" + re.escape(prefix) + "([0-9]+)$")
        max_no = 0
        for r in rows:
            m = pat.match(str(r["code"]).strip().upper())
            if m:
                max_no = max(max_no, int(m.group(1)))
        return max_no

    # -- linked-transaction guards -----------------------------------------
    def code_has_linked_transactions(self, code: str) -> bool:
        checks = [
            ("daybook", "accode"), ("daybookpart", "accode"), ("daybookratewgt", "accode"),
            ("oglist", "accode"), ("salesm", "custcode"), ("orderm", "custcode"),
        ]
        for table, column in checks:
            if not self.has_table(table) or column not in self.columns(table):
                continue
            if self.db.fetchone(
                f"SELECT 1 FROM {table} WHERE {column} = :c LIMIT 1", {"c": code}
            ):
                return True
        return False

    def daybook_has_accode(self, code: str) -> bool:
        if not self.has_table("daybook"):
            return False
        return self.db.fetchone(
            "SELECT 1 FROM daybook WHERE accode = :c LIMIT 1", {"c": code}
        ) is not None

    # -- writes (run inside a caller transaction) ---------------------------
    def insert_client(self, tx: Tx, row: dict) -> None:
        cols = ", ".join(row)
        binds = ", ".join(f":{k}" for k in row)
        tx.execute(f"INSERT INTO clients ({cols}) VALUES ({binds})", row)

    def update_client(self, tx: Tx, code: str, row: dict) -> None:
        sets = ", ".join(f"{k} = :{k}" for k in row if k != "code")
        if not sets:
            return
        params = {k: v for k, v in row.items() if k != "code"}
        params["_code"] = code
        tx.execute(f"UPDATE clients SET {sets} WHERE code = :_code", params)

    def upsert_accountm(self, tx: Tx, row: dict) -> None:
        """Insert or update accountm by accode (upsertAccountM)."""
        code = row["accode"]
        exists = tx.scalar(
            "SELECT 1 FROM accountm WHERE accode = :c LIMIT 1", {"c": code}
        ) is not None
        if exists:
            upd = {k: v for k, v in row.items() if k != "accode"}
            if not upd:
                return
            sets = ", ".join(f"{k} = :{k}" for k in upd)
            upd["_code"] = code
            tx.execute(f"UPDATE accountm SET {sets} WHERE accode = :_code", upd)
        else:
            cols = ", ".join(row)
            binds = ", ".join(f":{k}" for k in row)
            tx.execute(f"INSERT INTO accountm ({cols}) VALUES ({binds})", row)

    def upsert_advanced(self, tx: Tx, code: str, normalized: dict) -> None:
        if not normalized:
            return
        exists = tx.scalar(
            "SELECT 1 FROM clients_advanced WHERE code = :c LIMIT 1", {"c": code}
        ) is not None
        if exists:
            sets = ", ".join(f"{k} = :{k}" for k in normalized)
            params = dict(normalized)
            params["_code"] = code
            tx.execute(f"UPDATE clients_advanced SET {sets} WHERE code = :_code", params)
        else:
            row = {"code": code, **normalized}
            cols = ", ".join(row)
            binds = ", ".join(f":{k}" for k in row)
            tx.execute(f"INSERT INTO clients_advanced ({cols}) VALUES ({binds})", row)

    def rename_code(self, tx: Tx, old: str, new: str) -> None:
        """Port of renameCustomerCode()."""
        if old == new:
            return
        tx.execute("UPDATE clients SET code = :n WHERE code = :o", {"n": new, "o": old})
        for table, col in [("accountm", "accode"), ("clientsgs", "code"),
                           ("clientspict", "code"), ("clients_advanced", "code")]:
            if self.has_table(table):
                tx.execute(f"UPDATE {table} SET {col} = :n WHERE {col} = :o", {"n": new, "o": old})

    def delete_client(self, tx: Tx, code: str) -> None:
        tx.execute("DELETE FROM clients WHERE code = :c", {"c": code})
        if self.has_table("accountm"):
            tx.execute("DELETE FROM accountm WHERE accode = :c", {"c": code})
        for table in ("clientsgs", "clientspict", "clients_advanced"):
            if self.has_table(table):
                tx.execute(f"DELETE FROM {table} WHERE code = :c", {"c": code})
