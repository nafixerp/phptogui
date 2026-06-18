"""Debit / Credit Note posting — port of DebitCreditNoteController.

Debit Note (D):  account -netamt, adjust +amt, tax SGST/CGST +tax/2 each.
Credit Note (C): account +netamt, adjust -amt, tax SGST/CGST -tax/2 each.
A ROUND row balances the slno to zero. vchno = DN/CN + counter.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum


class NoteError(Exception):
    pass


class DebitCreditNoteService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def build_lines(self, stype: str, accode: str, adjac: str, amt, netamt, taxamt) -> list[dict]:
        stype = str(stype or "D").strip().upper()
        accode = str(accode or "").strip().upper()
        adjac = str(adjac or "").strip().upper()
        amt = money(amt); netamt = money(netamt); taxamt = money(taxamt)
        lines = []

        def add(ac, amount, op=""):
            a = money(amount)
            if not ac or a == 0:
                return
            lines.append({"accode": ac, "amount": a, "opaccode": op})

        if stype == "D":
            add(accode, money(-netamt))
            add(adjac, money(amt), accode)
        else:
            add(accode, netamt)
            add(adjac, money(-amt), accode)
        if taxamt > 0:
            half = money(taxamt / 2)
            sign = half if stype == "D" else money(-half)
            add("SGST", sign, accode)
            add("CGST", sign, accode)
        # ROUND to balance
        total = zero_sum(lines)
        if money(total) != 0:
            add("ROUND", money(-total), accode)
        return lines

    def save(self, stype: str, accode: str, adjac: str, amt, netamt, taxamt=0,
             tdate: str = "", particular: str = "") -> dict:
        if not self.pe.db.table_exists("daybook"):
            raise NoteError("daybook table not found")
        stype = str(stype or "D").strip().upper()
        if stype not in ("D", "C"):
            raise NoteError("Type must be D (debit note) or C (credit note)")
        if str(accode or "").strip() == "" or str(adjac or "").strip() == "":
            raise NoteError("Account and adjustment account are required")
        lines = self.build_lines(stype, accode, adjac, amt, netamt, taxamt)
        with self.pe.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            vchno = self.pe.reserve_voucher(tx, "DN/" if stype == "D" else "CN/",
                                            "VCHNODN" if stype == "D" else "VCHNOCN")
            label = "Debit Note" if stype == "D" else "Credit Note"
            part = (particular or f"{label} to {str(accode).strip().upper()} - {vchno}").upper()[:70]
            if self.pe.db.table_exists("daybookpart"):
                self.pe.insert_daybookpart(tx, {"slno": slno, "vchno": vchno, "particular": part,
                                                "tdate": tdate or None, "control": self.control})
            sno = 1
            for ln in lines:
                self.pe.insert_daybook_line(tx, {"slno": slno, "sno": sno, "tdate": tdate or None,
                                                 "accode": ln["accode"], "amount": ln["amount"],
                                                 "control": self.control, "opaccode": ln["opaccode"]})
                sno += 1
        log_delpart(self.pe.db, self.session, f"{label}({vchno})", utype="A", ttype="R")
        return {"slno": slno, "vchno": vchno, "message": f"{label} saved successfully"}
