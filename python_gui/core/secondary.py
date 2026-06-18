"""Secondary database sync (simplified port of app/Support/SecondaryDatabaseSync).

Mirrors a transaction's ledger rows from the primary DB to the configured
secondary company DB (DB_SECONDARY_DATABASE, e.g. "deom12"). Gated by the
ALLOWSECONDARYDBSYNC permission. This is a focused port: it copies the
daybook + daybookpart rows for a given slno (delete-then-insert on the target),
which covers receipt/payment/journal/sales/purchase vouchers.
"""

from __future__ import annotations

from .auth import AppSession
from .db import Database, secondary_db


def user_can_use(session: AppSession | None) -> bool:
    """ALLOWSECONDARYDBSYNC is a granted permission (NOT in userd blocked set)."""
    if session is None:
        return False
    # In the permission model, presence in userd = blocked; absence = allowed.
    return not session.is_blocked("ALLOWSECONDARYDBSYNC") and secondary_db() is not None


class SecondaryDatabaseSync:
    def __init__(self, primary: Database, target: Database | None = None):
        self.primary = primary
        self.target = target or secondary_db()

    def target_database_name(self) -> str:
        return self.target.database if self.target else ""

    def available(self) -> bool:
        return self.target is not None

    def _copy_table(self, table: str, slno: int) -> int:
        if not self.primary.table_exists(table) or not self.target.table_exists(table):
            return 0
        rows = self.primary.fetchall(f"SELECT * FROM {table} WHERE slno = :s", {"s": slno})
        with self.target.transaction() as tx:
            tx.execute(f"DELETE FROM {table} WHERE slno = :s", {"s": slno})
            for r in rows:
                cols = ", ".join(r.keys())
                binds = ", ".join(f":{k}" for k in r.keys())
                tx.execute(f"INSERT INTO {table} ({cols}) VALUES ({binds})", dict(r))
        return len(rows)

    def sync(self, module: str, slno: int) -> dict:
        if not self.available():
            return {"ok": False, "database": "", "message": "No secondary database configured"}
        copied = 0
        for table in ("daybook", "daybookpart", "daybookratewgt", "pdclist"):
            copied += self._copy_table(table, int(slno))
        return {"ok": True, "database": self.target_database_name(), "rows": copied,
                "message": f"Synced {copied} row(s) to {self.target_database_name()}"}
