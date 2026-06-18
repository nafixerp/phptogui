"""Staff Transaction (non-salary) — port of StaffTransactionController::save.

A journal-style voucher: each staff item posts to the staff account
(isDebit -> negative, else positive) with opaccode = the contra cash/bank
account; the contra account then takes the opposite of the total. Balances to
zero. vchno = JLB//JLE/ via VCHNOJB/VCHNOJE.

(The salary-allocation path with SALCUT/SALADD legs is a documented follow-on.)
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum


class StaffError(Exception):
    pass


class StaffTransactionService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def build_lines(self, items: list[dict], accode: str, is_debit: bool) -> list[dict]:
        accode = str(accode or "CASH").strip().upper() or "CASH"
        lines: list[dict] = []
        dtamt = Decimal("0")
        for it in items:
            code = str(it.get("code") or "").strip().upper()
            amount = money(it.get("amount", 0))
            if code == "" or amount <= 0:
                continue
            dac = money(-amount) if is_debit else money(amount)
            lines.append({"accode": code, "amount": dac, "opaccode": accode})
            dtamt += amount
        if not lines:
            raise StaffError("No items to save")
        max_ac = max((ln["accode"] for ln in lines), default="")
        contra = money(dtamt) if is_debit else money(-dtamt)
        lines.append({"accode": accode, "amount": contra, "opaccode": max_ac})
        return lines

    def save(self, items: list[dict], accode: str = "CASH", is_debit: bool = True,
             tdate: str = "", particular: str = "") -> dict:
        if not self.pe.db.table_exists("daybook"):
            raise StaffError("daybook table not found")
        lines = self.build_lines(items, accode, is_debit)
        assert zero_sum(lines) == Decimal("0.00")
        with self.pe.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            if self.control == 1:
                vchno = "JLB/" + str(self.pe.increment_gen_int(tx, "VCHNOJB")).rjust(5, "0")
            else:
                vchno = "JLE/" + str(self.pe.increment_gen_int(tx, "VCHNOJE")).rjust(5, "0")
            part = (particular or f"By Journal entry {vchno}").strip()[:40]
            if self.pe.db.table_exists("daybookpart"):
                self.pe.insert_daybookpart(tx, {
                    "slno": slno, "vchno": vchno, "particular": part, "tdate": tdate or None,
                    "control": self.control, "uid": (self.session.user_code if self.session else "")})
            sno = 1
            for ln in lines:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": tdate or None, "accode": ln["accode"],
                    "amount": ln["amount"], "control": self.control, "opaccode": ln["opaccode"]})
                sno += 1
        log_delpart(self.pe.db, self.session, f"Staff Transaction({vchno})", utype="A", ttype="R")
        return {"slno": slno, "vchno": vchno, "lines": len(lines), "message": "Staff transaction saved"}
