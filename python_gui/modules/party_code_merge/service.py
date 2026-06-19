"""Party Code Merge — port of PartyCodeMergeController::merge.

Merges one or more *source* party codes into a single *target*: every table that
references a party code is re-keyed source→target (the ``REFERENCE_MAP``), the
source accounts' opening balances are carried into the target, and the source
master rows are either deleted or zeroed. All table/column references are
guarded against the live schema and run inside one transaction.

This is a high-blast-radius operation — every write is column/table guarded and
the whole merge is atomic (rolls back on any error).
"""

from __future__ import annotations

from ...core.auth import AppSession
from ...core.db import Database

# (table, column) pairs that hold a party code (port of REFERENCE_MAP)
REFERENCE_MAP = [
    ("daybook", "accode"), ("daybook", "opaccode"), ("daybook", "cbcode"), ("daybook", "cocode"),
    ("salesm", "custcode"), ("salesm", "cbcode"), ("salesm", "cocode"),
    ("salesrm", "custcode"), ("orderm", "custcode"), ("orderm", "cbcode"), ("orderm", "cocode"),
    ("repairm", "custcode"), ("purchasem", "suppcode"), ("purchaserm", "suppcode"),
    ("clients", "cocode"), ("collection", "code"), ("collection", "cbcode"),
    ("loan", "ccode"), ("loan", "cbcode"), ("loancolln", "ccode"), ("loancolln", "cbcode"),
    ("pdclist", "code"), ("kuricolln", "code"), ("kuriint", "code"), ("kurifinishdet", "code"),
    ("suspentry", "accode"),
]
# source master tables to delete (order: child tables first)
SOURCE_MASTERS = [("clientspict", "code"), ("clients_advanced", "code"),
                  ("clientsgs", "code"), ("clients", "code"), ("accountm", "accode")]
ACCOUNT_SUM_COLUMNS = ["opbal", "opbalb", "opwgt", "opwgtb"]


class PartyCodeMergeError(Exception):
    pass


class PartyCodeMergeService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def _has(self, table: str, col: str) -> bool:
        return self.db.table_exists(table) and self.db.column_exists(table, col)

    def merge(self, sources: list[str], target: str, delete_sources: bool = True) -> dict:
        target = str(target).strip().upper()
        sources = [str(s).strip().upper() for s in sources if str(s).strip()]
        sources = [s for s in sources if s != target]
        if not target:
            raise PartyCodeMergeError("Target code required")
        if not sources:
            raise PartyCodeMergeError("At least one source code required")

        updated = 0
        with self.db.transaction() as tx:
            balances_moved = self._carry_opening(tx, sources, target)
            for table, col in REFERENCE_MAP:
                if not self._has(table, col):
                    continue
                ph = ", ".join(f":s{i}" for i in range(len(sources)))
                params = {f"s{i}": v for i, v in enumerate(sources)}
                cnt = tx.scalar(
                    f"SELECT COUNT(*) FROM {table} WHERE TRIM({col}) IN ({ph})", params) or 0
                if int(cnt) <= 0:
                    continue
                tx.execute(f"UPDATE {table} SET {col} = :t WHERE TRIM({col}) IN ({ph})",
                           {"t": target, **params})
                updated += int(cnt)
            if delete_sources:
                self._cleanup(tx, sources)
        return {"target": target, "sources": sources,
                "reference_rows_updated": updated, "opening_balances_moved": balances_moved}

    def _carry_opening(self, tx, sources: list[str], target: str) -> int:
        if not self.db.table_exists("accountm"):
            return 0
        cols = [c for c in ACCOUNT_SUM_COLUMNS if self.db.column_exists("accountm", c)]
        if not cols:
            return 0
        if not tx.fetchall("SELECT 1 FROM accountm WHERE TRIM(accode) = :t LIMIT 1", {"t": target}):
            return 0
        ph = ", ".join(f":s{i}" for i in range(len(sources)))
        params = {f"s{i}": v for i, v in enumerate(sources)}
        src = tx.fetchall(
            f"SELECT {', '.join(f'COALESCE(SUM({c}),0) AS {c}' for c in cols)}, COUNT(*) AS n "
            f"FROM accountm WHERE TRIM(accode) IN ({ph})", params)
        if not src or int(src[0].get("n") or 0) == 0:
            return 0
        sums = src[0]
        sets = ", ".join(f"{c} = COALESCE({c},0) + :{c}" for c in cols)
        tx.execute(f"UPDATE accountm SET {sets} WHERE TRIM(accode) = :t",
                   {**{c: sums.get(c) for c in cols}, "t": target})
        return int(sums.get("n") or 0)

    def _cleanup(self, tx, sources: list[str]) -> None:
        ph = ", ".join(f":s{i}" for i in range(len(sources)))
        params = {f"s{i}": v for i, v in enumerate(sources)}
        for table, col in SOURCE_MASTERS:
            if self._has(table, col):
                tx.execute(f"DELETE FROM {table} WHERE TRIM({col}) IN ({ph})", params)
