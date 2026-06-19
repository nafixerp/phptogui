"""Payment Confirmation — port of PaymentConfirmationController.

Lists provisional payment vouchers (``daybook.control = 4`` with a ``VP`` voucher
prefix and a negative amount) and confirms one by promoting its daybook (and any
``pdclist``) rows to ``control = 1`` and logging to ``delpart``. Gated by the
``ALLOWPMNTCONFIRMATION`` permission.
"""

from __future__ import annotations

from datetime import date, datetime

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money

PENDING_CONTROL = 4
LIVE_CONTROL = 1
PERMISSION = "ALLOWPMNTCONFIRMATION"


class PaymentConfirmationError(Exception):
    pass


class PaymentConfirmationService:
    def __init__(self, database: Database, session: AppSession | None = None, control: int = 1):
        self.db = database
        self.session = session
        self.control = control if control in (1, 2) else 1

    def can_confirm(self) -> bool:
        if self.session is None:
            return True
        is_blocked = getattr(self.session, "is_blocked", None)
        # ALLOWPMNTCONFIRMATION is an allow-flag in userd; treat blocked_items as the gate
        return not (callable(is_blocked) and is_blocked(PERMISSION))

    def pending(self) -> list[dict]:
        if not (self.db.table_exists("daybook") and self.db.table_exists("daybookpart")):
            return []
        rows = self.db.fetchall(
            "SELECT daybookpart.vchno, daybook.tdate, daybook.accode, daybook.opaccode, "
            "daybook.amount, daybookpart.particular, daybook.slno "
            "FROM daybook JOIN daybookpart ON daybook.slno = daybookpart.slno "
            "WHERE daybook.control = :pc AND daybookpart.vchno LIKE 'VP%' AND daybook.amount < 0 "
            "ORDER BY daybook.tdate, daybook.slno LIMIT 2000", {"pc": PENDING_CONTROL})
        return [{"vchno": str(r.get("vchno") or "").strip(), "tdate": str(r.get("tdate") or ""),
                 "accode": str(r.get("accode") or "").strip(), "amount": money(abs(money(r.get("amount")))),
                 "particular": str(r.get("particular") or "").strip(), "slno": r.get("slno")} for r in rows]

    def confirm(self, slno: int, vchno: str = "") -> str:
        if not self.can_confirm():
            raise PaymentConfirmationError("You are not allowed to update this module")
        slno = int(slno)
        if slno <= 0:
            raise PaymentConfirmationError("No entry selected")
        if not self.db.table_exists("daybook"):
            raise PaymentConfirmationError("daybook table not found")
        uid = getattr(self.session, "user_code", "") if self.session else ""
        with self.db.transaction() as tx:
            tdate = tx.scalar("SELECT MAX(tdate) FROM daybook WHERE slno = :s", {"s": slno}) or date.today().isoformat()
            if self.db.table_exists("pdclist"):
                tx.execute("UPDATE pdclist SET control = :c WHERE slno = :s", {"c": LIVE_CONTROL, "s": slno})
            tx.execute("UPDATE daybook SET control = :c WHERE slno = :s", {"c": LIVE_CONTROL, "s": slno})
            if self.db.table_exists("delpart"):
                self._log(tx, tdate, vchno, slno, uid)
        return f"Entry confirmed: {vchno}"

    def _log(self, tx, tdate, vchno, slno, uid) -> None:
        cols = set(self.db.columns("delpart"))
        row = {"tdate": tdate, "part": f"Payment Entry({str(vchno).strip()}) Confirmed-{tdate}",
               "control": self.control, "slno": slno, "utype": "C", "ttype": "VH",
               "updtdate": date.today().isoformat(), "updttime": datetime.now().strftime("%H:%M:%S"),
               "uid": uid, "ic": uid}
        use = {k: v for k, v in row.items() if k in cols}
        if not use:
            return
        names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
        tx.execute(f"INSERT INTO delpart ({names}) VALUES ({binds})", use)
