"""Account Master repository — SQL against `accountm` / `accountg` / `accountgbs`.

Source: app/Http/Controllers/AccountMasterController.php + docs/accounting-
posting-logic.md. Frozen schema: `AccountM(accode CHAR(8) PK, name, actype1,
actype2, reserve, grcode, opbal, opbalb, control, hlp, ..., bshead, shepos,
shedgrp, sp, removed, blocked, note, opwgt, opwgtb)`.

`actype1` ∈ {R,E,A,L} (revenue/expense/asset/liability). `actype2` markers:
H=cash, B=bank, C/S/G/R/J=linked party accounts (managed via the party master,
not here). Opening balance: debit stored negative, credit positive; the active
column is `opbal` at gilevel 1 else `opbalb`.
"""

from __future__ import annotations

from ...core.db import Database, Tx

# Columns AccountMasterController::loadAccountRow selects (when present).
_LOAD_COLS = [
    "name", "opbal", "opbalb", "actype1", "actype2", "control", "reserve",
    "grcode", "hlp", "tplpos", "bshead", "shepos", "shedgrp", "sp", "removed",
    "blocked", "note",
]
# actype2 markers for accounts owned by the party master (excluded here).
_PARTY_TYPES = ("C", "S", "G", "R", "J")


class AccountMasterRepo:
    def __init__(self, database: Database):
        self.db = database

    # -- schema helpers -----------------------------------------------------
    def has_table(self, table: str) -> bool:
        return self.db.table_exists(table)

    def has_column(self, table: str, column: str) -> bool:
        return self.db.column_exists(table, column)

    def columns(self, table: str) -> set[str]:
        return set(self.db.columns(table))

    def filter_columns(self, table: str, row: dict) -> dict:
        cols = self.columns(table)
        return {k: v for k, v in row.items() if k.lower() in cols}

    # -- reads --------------------------------------------------------------
    def account_exists(self, accode: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM accountm WHERE TRIM(accode) = :c LIMIT 1", {"c": accode.strip()}
        ) is not None

    def load_account(self, accode: str) -> dict | None:
        accode = accode.strip()
        if accode == "":
            return None
        cols = [c for c in _LOAD_COLS if self.has_column("accountm", c)]
        if not cols:
            return None
        return self.db.fetchone(
            f"SELECT {', '.join(cols)} FROM accountm WHERE TRIM(accode) = :c LIMIT 1",
            {"c": accode},
        )

    def list_accounts(self, search: str = "", limit: int = 300) -> list[dict]:
        """Master-managed accounts: exclude party-linked + removed (apiAccount list_all)."""
        sql = "SELECT TRIM(accode) AS accode, TRIM(name) AS name, grcode, actype1, actype2 FROM accountm WHERE 1=1"
        params: dict = {}
        if self.has_column("accountm", "removed"):
            sql += " AND (removed <> 1 OR removed IS NULL)"
        if self.has_column("accountm", "actype2"):
            placeholders = ", ".join(f":p{i}" for i in range(len(_PARTY_TYPES)))
            sql += f" AND actype2 NOT IN ({placeholders})"
            params.update({f"p{i}": t for i, t in enumerate(_PARTY_TYPES)})
        if search:
            params["s"] = f"%{search}%"
            sql += " AND (TRIM(accode) LIKE :s OR TRIM(name) LIKE :s)"
        sql += " ORDER BY accode LIMIT :lim"
        params["lim"] = max(1, min(limit, 500))
        return self.db.fetchall(sql, params)

    def list_groups(self, search: str = "") -> list[dict]:
        sql = "SELECT TRIM(grcode) AS grcode, TRIM(name) AS name FROM accountg"
        params: dict = {}
        if search:
            params["s"] = f"%{search}%"
            sql += " WHERE TRIM(grcode) LIKE :s OR TRIM(name) LIKE :s"
        sql += " ORDER BY name"
        return self.db.fetchall(sql, params)

    def list_bs_heads(self) -> list[dict]:
        return self.db.fetchall(
            "SELECT TRIM(hcode) AS hcode, TRIM(hname) AS hname FROM accountgbs ORDER BY hname"
        )

    def account_meta(self, accode: str) -> dict | None:
        return self.db.fetchone(
            "SELECT reserve, actype2 FROM accountm WHERE TRIM(accode) = :c LIMIT 1",
            {"c": accode.strip()},
        )

    def daybook_amount_total(self, accode: str) -> float:
        """SUM(ABS(amount)) else COUNT(*) for the account (validateAccount delete)."""
        if not self.has_table("daybook"):
            return 0.0
        expr = "SUM(ABS(amount))" if self.has_column("daybook", "amount") else "COUNT(*)"
        val = self.db.scalar(
            f"SELECT COALESCE({expr}, 0) FROM daybook WHERE TRIM(accode) = :c", {"c": accode.strip()}
        )
        try:
            return float(val or 0)
        except (TypeError, ValueError):
            return 0.0

    def daybook_count(self, accode: str) -> int:
        if not self.has_table("daybook") or not self.has_column("daybook", "accode"):
            return 0
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM daybook WHERE TRIM(accode) = :c", {"c": accode.strip()}
        ) or 0)

    # -- writes (inside a caller transaction) -------------------------------
    def insert_account(self, tx: Tx, row: dict) -> None:
        cols = ", ".join(row)
        binds = ", ".join(f":{k}" for k in row)
        tx.execute(f"INSERT INTO accountm ({cols}) VALUES ({binds})", row)

    def update_account(self, tx: Tx, where_code: str, row: dict) -> None:
        sets = ", ".join(f"{k} = :{k}" for k in row)
        params = dict(row)
        params["_where"] = where_code
        tx.execute(f"UPDATE accountm SET {sets} WHERE TRIM(accode) = :_where", params)

    def update_shedgrp_refs(self, tx: Tx, old_code: str, new_code: str) -> None:
        tx.execute(
            "UPDATE accountm SET shedgrp = :new WHERE TRIM(shedgrp) = :old",
            {"new": new_code, "old": old_code},
        )

    def delete_account(self, tx: Tx, accode: str) -> int:
        res = tx.execute("DELETE FROM accountm WHERE TRIM(accode) = :c", {"c": accode.strip().upper()})
        return getattr(res, "rowcount", 0)
