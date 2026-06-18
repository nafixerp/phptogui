"""Purchase Bill Confirmation — port of PurchaseBillConfirmationController.

Pending bills are the *provisional* purchases (``control = 4`` and ``pr = 'P'``).
Confirming a bill promotes it to live (``control = 1``) across every related
table, then logs the action in ``delpart``. The reversal/delete path is a
documented follow-on (handled by the Purchase entry screen).

Source: PurchaseBillConfirmationController::load / confirm.
"""

from __future__ import annotations

from datetime import date, datetime

from ...core.auth import AppSession
from ...core.db import Database

PENDING_CONTROL = 4   # provisional marker
LIVE_CONTROL = 1      # confirmed / live

# tables PurchaseBillConfirmationController flips control on (slno-keyed)
_RELATED = ["purchasem", "purchaserm", "advafter", "pdclist", "stkandprofit", "daybook"]


class ConfirmError(Exception):
    pass


class PurchaseConfirmationService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def pending(self, date1: str | None = None, date2: str | None = None) -> list[dict]:
        if not self.db.table_exists("purchasem"):
            return []
        cols = set(self.db.columns("purchasem"))
        if "control" not in cols or "pr" not in cols:
            return []
        net = "netamt" if "netamt" in cols else "billamt"
        pamt = "pamt" if "pamt" in cols else "0"
        billno = "billno" if "billno" in cols else "NULL"
        docno = "docno" if "docno" in cols else "NULL"
        where = ["control = :pc", "pr = 'P'"]
        params: dict = {"pc": PENDING_CONTROL}
        if date1 and date2 and "tdate" in cols:
            where.append("tdate BETWEEN :f AND :t"); params.update(f=date1, t=date2)
        return self.db.fetchall(
            f"SELECT slno, {docno} AS docno, tdate, {billno} AS billno, "
            f"TRIM(COALESCE(name,'')) AS name, suppcode, "
            f"COALESCE(billamt,0) AS billamt, COALESCE({net},0) AS netamt, "
            f"COALESCE({pamt},0) AS pamt, "
            f"(COALESCE({net},0) - COALESCE({pamt},0)) AS balance "
            f"FROM purchasem WHERE {' AND '.join(where)} "
            "ORDER BY tdate, slno, docno LIMIT 1000", params)

    def confirm(self, slno: int) -> str:
        if not self.db.table_exists("purchasem"):
            raise ConfirmError("purchasem table not found")
        slno = int(slno)
        bill = self.db.fetchone(
            "SELECT slno, tdate, docno, billno FROM purchasem WHERE slno = :s LIMIT 1",
            {"s": slno})
        if not bill:
            raise ConfirmError("Bill not found")

        docno = str(bill.get("docno") or "").strip()
        billno = str(bill.get("billno") or "").strip()
        tdate = bill.get("tdate")
        uid = getattr(self.session, "user_code", "") if self.session else ""

        with self.db.transaction() as tx:
            for table in _RELATED:
                if self.db.table_exists(table) and self.db.column_exists(table, "control"):
                    tx.execute(f"UPDATE {table} SET control = :c WHERE slno = :s",
                               {"c": LIVE_CONTROL, "s": slno})
            if self.db.table_exists("delpart"):
                self._log(tx, tdate, billno, docno, slno, uid)
        return f"Confirmed: {docno or billno or slno}"

    def _log(self, tx, tdate, billno, docno, slno, uid) -> None:
        cols = set(self.db.columns("delpart"))
        part = f"Purchase Entry({billno} - {docno}) Confirmed-{tdate}"
        row = {
            "tdate": tdate, "part": part, "control": LIVE_CONTROL, "slno": slno,
            "utype": "C", "ttype": "P", "updtdate": date.today().isoformat(),
            "updttime": datetime.now().strftime("%H:%M:%S"), "uid": uid, "ic": uid,
        }
        use = {k: v for k, v in row.items() if k in cols}
        if not use:
            return
        names = ", ".join(use)
        binds = ", ".join(f":{k}" for k in use)
        tx.execute(f"INSERT INTO delpart ({names}) VALUES ({binds})", use)
