"""Amount ⇄ Weight Transfer — port of AmtWgtTransferController::save.

Books a conversion between a party's cash and metal-weight balances as a journal
voucher (JLB//JLE/): two daybook lines (the ``ATOW`` control account and the
party, always summing to zero) plus a ``daybookratewgt`` weight movement. The
sign of both the daybook party line and the weight depends on direction
(Amt→Wgt vs Wgt→Amt).
"""

from __future__ import annotations

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money, weight as wq
from ...core.posting import PostingEngine, zero_sum

_ATOW = "ATOW"


class AmtWgtTransferError(Exception):
    pass


class AmtWgtTransferService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.db = engine.db
        self.session = session
        self.control = control if control in (1, 2) else 1

    def _insert(self, tx, table: str, row: dict) -> None:
        cols = set(self.db.columns(table))
        use = {k: v for k, v in row.items() if k in cols}
        if not use:
            return
        names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
        tx.execute(f"INSERT INTO {table} ({names}) VALUES ({binds})", use)

    def save(self, *, tdate: str, code: str, amt, weight, rate=0, ttype: str = "Amt To Wgt") -> dict:
        if not tdate:
            raise AmtWgtTransferError("Date required")
        code = str(code).strip().upper()
        if not code:
            raise AmtWgtTransferError("Party required")
        amt = money(amt); wgt = wq(weight); rate = money(rate)
        if amt <= 0 or wgt <= 0:
            raise AmtWgtTransferError("Nothing to do")
        if not self.db.table_exists("daybook"):
            raise AmtWgtTransferError("daybook table not found")
        is_a2w = ttype == "Amt To Wgt"
        uid = getattr(self.session, "user_code", "") if self.session else ""
        prefix, counter = ("JLB/", "VCHNOJB") if self.control == 1 else ("JLE/", "VCHNOJE")
        label = "Amt To Wgt" if is_a2w else "Wgt To Amt"
        desc = f"By {label} Entry {code} {wgt:.3f} X {rate:.2f}"

        with self.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            docno = f"{prefix}{self.pe.increment_gen_int(tx, counter):05d}"
            self._insert(tx, "daybookpart", {
                "slno": slno, "vchno": docno, "particular": desc[:200], "ic": uid, "uid": uid})
            if self.db.table_exists("daybookratewgt"):
                self._insert(tx, "daybookratewgt", {
                    "slno": slno, "rate": rate, "mcp": 0,
                    "wgt": wq(-wgt) if is_a2w else wgt, "code": code,
                    "tdate": tdate, "control": self.control})
            # Amt→Wgt: ATOW -amt, party +amt ; Wgt→Amt: ATOW +amt, party -amt
            atow_amt = money(-amt) if is_a2w else amt
            party_amt = money(-atow_amt)
            lines = [{"accode": _ATOW, "amount": atow_amt}, {"accode": code, "amount": party_amt}]
            sno = 1
            for ln in lines:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": tdate, "accode": ln["accode"],
                    "amount": ln["amount"], "control": self.control,
                    "opaccode": code if ln["accode"] == _ATOW else _ATOW})
                sno += 1
        return {"slno": slno, "docno": docno, "balanced": money(zero_sum(lines)) == 0}
