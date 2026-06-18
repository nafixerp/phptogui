"""Expense Voucher posting — port of ExpenseVoucherEntryController::save.

Lines (control 0): expense account -bamt, tax -taxamt, discount +discount,
cash/bank +paidamt, party +netamt and party -paidamt. A ROUND row balances.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum


class ExpenseError(Exception):
    pass


class ExpenseVoucherService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 0):
        self.pe = engine
        self.session = session
        self.control = int(control)

    def build_lines(self, d: dict) -> list[dict]:
        pamt_ac = str(d.get("pamtAc") or "EP").strip().upper() or "EP"
        tax_ac = str(d.get("taxAc") or "ETAX").strip().upper() or "ETAX"
        disc_ac = str(d.get("discAc") or "PDISC").strip().upper() or "PDISC"
        cb_ac = str(d.get("cbAc") or "CASH").strip().upper() or "CASH"
        party = str(d.get("partyCode") or "").strip().upper()
        bamt = money(d.get("bamt", 0))
        taxamt = money(d.get("taxamt", 0))
        discount = money(d.get("discount", 0))
        paidamt = money(d.get("paidamt", 0))
        netamt = money(d.get("netamt", money(bamt + taxamt - discount)))
        lines = []

        def add(ac, amount):
            a = money(amount)
            if not ac or a == 0:
                return
            lines.append({"accode": ac, "amount": a})

        if bamt > 0:
            add(pamt_ac, money(-bamt))
        if taxamt > 0:
            add(tax_ac, money(-taxamt))
        if discount > 0:
            add(disc_ac, discount)
        if paidamt > 0:
            add(cb_ac, paidamt)
        if party != "":
            add(party, netamt)
            if paidamt > 0:
                add(party, money(-paidamt))
        total = zero_sum(lines)
        if money(total) != 0:
            add("ROUND", money(-total))
        return lines

    def save(self, d: dict, tdate: str = "") -> dict:
        if not self.pe.db.table_exists("daybook"):
            raise ExpenseError("daybook table not found")
        if money(d.get("bamt", 0)) <= 0:
            raise ExpenseError("Bill amount required")
        lines = self.build_lines(d)
        with self.pe.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            vchno = self.pe.reserve_voucher(tx, "EXP/", "VCHNOEXP")
            if self.pe.db.table_exists("daybookpart"):
                self.pe.insert_daybookpart(tx, {
                    "slno": slno, "vchno": vchno, "tdate": tdate or None, "control": self.control,
                    "particular": (str(d.get("particular") or f"Expense {vchno}")).upper()[:70]})
            sno = 1
            for ln in lines:
                self.pe.insert_daybook_line(tx, {"slno": slno, "sno": sno, "tdate": tdate or None,
                                                 "accode": ln["accode"], "amount": ln["amount"],
                                                 "control": self.control})
                sno += 1
        log_delpart(self.pe.db, self.session, f"Expense Voucher({vchno})", utype="A", ttype="R")
        return {"slno": slno, "vchno": vchno, "lines": len(lines), "message": "Expense voucher saved"}
