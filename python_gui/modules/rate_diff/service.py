"""Rate-Difference Adjustment — port of RateDiffAdjustmentController::save.

Books a rate-difference as a two-line journal: RDIFF debited (+diffamt) and the
party credited (-diffamt), under a JLB//JLE/ voucher by control level. When the
adjustment is tied to a bill (``billno`` + ``islno``) a ``collection`` row is
written too. Always zero-sum (the two daybook lines net to zero).
"""

from __future__ import annotations

from decimal import Decimal

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money, to_decimal
from ...core.posting import PostingEngine, zero_sum


class RateDiffError(Exception):
    pass


class RateDiffService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.db = engine.db
        self.session = session
        self.control = control if control in (1, 2) else 1

    def save(self, *, tdate: str, code: str, diffamt, billno: str = "", weight=0,
             newrate=0, islno: int = 0, bill_control: int = 0) -> dict:
        if not self.db.table_exists("daybook"):
            raise RateDiffError("daybook table not found")
        code = str(code).strip().upper()
        billno = str(billno).strip().upper()
        diffamt = money(diffamt)
        if not tdate:
            raise RateDiffError("Date required")
        if not code:
            raise RateDiffError("Party required")
        if diffamt <= 0:
            raise RateDiffError("Nothing to do. Diff amount must be > 0")

        icontrol = int(bill_control) if int(bill_control) > 0 else self.control
        uid = getattr(self.session, "user_code", "") if self.session else ""
        prefix, counter = ("JLB/", "VCHNOJB") if self.control == 1 else ("JLE/", "VCHNOJE")

        wt = to_decimal(weight) or Decimal("0")
        rate = to_decimal(newrate) or Decimal("0")
        desc = f"By Rate Diff Entry {code}"
        desc += f" {billno}" if billno else f" {wt:.3f} X {rate:.2f}"

        lines = [{"accode": "RDIFF", "amount": diffamt},
                 {"accode": code, "amount": money(-diffamt)}]

        with self.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            docno = f"{prefix}{self.pe.increment_gen_int(tx, counter):05d}"
            self.pe.insert_daybookpart(tx, {
                "slno": slno, "vchno": docno, "particular": desc[:200], "ic": uid, "uid": uid})
            sno = 1
            for ln in lines:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": tdate, "accode": ln["accode"],
                    "amount": ln["amount"], "control": icontrol})
                sno += 1
            if billno and int(islno) > 0 and self.db.table_exists("collection"):
                self._collection(tx, slno, code, tdate, billno, diffamt, icontrol, islno, rate)

        return {"slno": slno, "docno": docno, "balanced": money(zero_sum(lines)) == 0}

    def _collection(self, tx, slno, code, tdate, billno, diffamt, icontrol, islno, rate) -> None:
        cols = set(self.db.columns("collection"))
        row = {"slno": slno, "code": code, "tdate": tdate, "billno": billno,
               "tranamt": money(-diffamt), "discount": Decimal("0"), "control": icontrol,
               "islno": int(islno), "grate": rate, "grate2": rate}
        use = {k: v for k, v in row.items() if k in cols}
        if not use:
            return
        names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
        tx.execute(f"INSERT INTO collection ({names}) VALUES ({binds})", use)
