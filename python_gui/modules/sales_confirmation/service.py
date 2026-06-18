"""Sales Bill Confirmation (status) — simplified port of SalesBillConfirmationController.

Lists unconfirmed sales bills and confirms one by setting salesm.status. (The
full confirm flow re-posts amended discount/tax; this module updates the
confirmation status, which is the core of the screen. Re-posting amendments is a
documented follow-on.)
"""

from __future__ import annotations

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.db import Database

CONFIRMED_STATUS = 2   # confirmed marker
UNCONFIRMED_STATUS = 1


class ConfirmError(Exception):
    pass


class SalesConfirmationService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def pending(self, date1: str, date2: str) -> list[dict]:
        if not self.db.table_exists("salesm"):
            return []
        cols = set(self.db.columns("salesm"))
        if "status" not in cols:
            return []
        net = "netamt" if "netamt" in cols else "billamt"
        return self.db.fetchall(
            f"SELECT slno, billno, tdate, TRIM(COALESCE(custname,'')) AS custname, "
            f"COALESCE({net},0) AS netamt, status FROM salesm "
            "WHERE tdate BETWEEN :f AND :t AND (status IS NULL OR status <> :cf) "
            "ORDER BY tdate, slno LIMIT 1000",
            {"f": date1, "t": date2, "cf": CONFIRMED_STATUS})

    def confirm(self, slno: int, confirmed: bool = True) -> str:
        if not self.db.table_exists("salesm"):
            raise ConfirmError("salesm table not found")
        slno = int(slno)
        if not self.db.fetchone("SELECT 1 FROM salesm WHERE slno = :s LIMIT 1", {"s": slno}):
            raise ConfirmError("Bill not found")
        st = CONFIRMED_STATUS if confirmed else UNCONFIRMED_STATUS
        self.db.execute("UPDATE salesm SET status = :st WHERE slno = :s", {"st": st, "s": slno})
        log_delpart(self.db, self.session, f"Sales Bill(slno {slno}) {'Confirmed' if confirmed else 'Unconfirmed'}",
                    utype="E", ttype="R")
        return "Bill confirmed" if confirmed else "Bill unconfirmed"
