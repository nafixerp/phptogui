"""Group Amount Allocation — port of GroupAmtAllocationController::save.

Distributes amounts across several accounts against one opposite (debit/credit)
account as a single journal voucher (JLB//JLE/). Each line posts +amount (when
``credited``) or -amount; the opposite account absorbs the negated total — so
the voucher is always zero-sum.
"""

from __future__ import annotations

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum


class GroupAmtAllocationError(Exception):
    pass


class GroupAmtAllocationService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.db = engine.db
        self.session = session
        self.control = control if control in (1, 2) else 1

    def save(self, *, tdate: str, opac: str, items: list[dict],
             credited: bool = True, particular: str = "") -> dict:
        if not tdate:
            raise GroupAmtAllocationError("Date required")
        opac = str(opac).strip().upper()
        if not opac:
            raise GroupAmtAllocationError("Debit/Credit A/c required")
        valid = [it for it in items if money(it.get("amount")) > 0]
        if not valid:
            raise GroupAmtAllocationError("No amounts to allocate")
        if not self.db.table_exists("daybook"):
            raise GroupAmtAllocationError("daybook table not found")
        uid = getattr(self.session, "user_code", "") if self.session else ""
        prefix, counter = ("JLB/", "VCHNOJB") if self.control == 1 else ("JLE/", "VCHNOJE")

        with self.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            docno = f"{prefix}{self.pe.increment_gen_int(tx, counter):05d}"
            part = (particular.strip() or f"By Journal entry {docno}")[:40]
            self.pe.insert_daybookpart(tx, {"slno": slno, "vchno": docno, "particular": part,
                                            "ic": uid, "uid": uid, "tdate": tdate})
            total = money(0); last_ac = ""; lines = []
            sno = 1
            for it in valid:
                accode = str(it.get("accode") or "").strip().upper()
                aclink = str(it.get("aclink") or "").strip()
                amt = money(it.get("amount"))
                use_code = aclink.upper() if aclink else accode
                opaccode = aclink if aclink else ""
                db_amt = amt if credited else money(-amt)
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": tdate, "accode": use_code,
                    "amount": db_amt, "control": self.control, "opaccode": opaccode})
                lines.append({"accode": use_code, "amount": db_amt})
                total += amt; last_ac = use_code; sno += 1
            op_amt = money(-total) if credited else total
            self.pe.insert_daybook_line(tx, {
                "slno": slno, "sno": sno, "tdate": tdate, "accode": opac,
                "amount": op_amt, "control": self.control, "opaccode": last_ac})
            lines.append({"accode": opac, "amount": op_amt})
        return {"slno": slno, "docno": docno, "total": total,
                "balanced": money(zero_sum(lines)) == 0}
