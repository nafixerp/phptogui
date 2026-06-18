"""Purchase Return posting — port of PurchaseReturnController writeDaybook.

Opposite of a purchase (opaccode='EP', vtype='PL'): EP debited (+billTotal),
supplier credited (-dacamt) then paid-back (+paid), cash/cheque credited if
refunded, ADD +others, tax reverses input credit (SGST/CGST/IGST positive), then
a ROUND row balances to zero.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum


class PurchaseReturnError(Exception):
    pass


def _m(d, k):
    return money(d.get(k, 0))


class PurchaseReturnService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def build_entries(self, d: dict) -> list[dict]:
        EP = "EP"
        supp = str(d.get("suppcode") or "").strip().upper()
        chq_bank = str(d.get("chq_bank") or "").strip().upper()
        chq_pdc = str(d.get("chq_pdc") or "N").strip().upper() == "Y"
        interstate = bool(d.get("interstate"))
        tax_ext = bool(d.get("tax_ext"))
        bill_total = _m(d, "bill_total")
        net_total = _m(d, "net_total")
        others = _m(d, "others")
        paid = _m(d, "paid_amount")
        chq = _m(d, "chq_amount")
        tax = _m(d, "tax")
        dacamt = money(net_total + others)
        cash_paid = money(paid - chq)
        entries: list[dict] = []

        def ins(accode, amount, op):
            amt = money(amount)
            if amt == 0:
                return
            entries.append({"accode": str(accode or "")[:20], "amount": amt, "opaccode": op[:20]})

        if bill_total > 0:
            ins(EP, bill_total, supp or EP)
        if dacamt != 0:
            ins(supp or EP, money(-dacamt), EP)
        if paid > 0:
            ins(supp or EP, paid, EP)
        if cash_paid > 0:
            ins("CASH", money(-cash_paid), EP)
        if chq > 0:
            ins("CNP" if chq_pdc else (chq_bank or "CASH"), money(-chq), EP)
        if others > 0:
            ins("ADD", others, EP)
        if tax > 0 and not tax_ext:
            if interstate:
                ins("IGST", tax, EP)
            else:
                half = money(tax / 2)
                ins("SGST", half, EP)
                ins("CGST", half, EP)
        return entries

    def post(self, slno: int, tdate: str, d: dict) -> dict:
        if not self.pe.db.table_exists("daybook"):
            raise PurchaseReturnError("daybook table not found")
        entries = self.build_entries(d)
        with self.pe.db.transaction() as tx:
            if not slno or int(slno) <= 0:
                slno = self.pe.next_serial_no(tx)
            if self.pe.db.table_exists("daybookpart"):
                self.pe.insert_daybookpart(tx, {
                    "slno": slno, "vchno": str(slno), "tdate": tdate, "control": self.control,
                    "particular": str(d.get("particular") or f"By Purchase Return {slno}")[:200],
                })
            sno = 1
            for e in entries:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": tdate, "accode": e["accode"],
                    "amount": e["amount"], "control": self.control, "opaccode": e["opaccode"], "vtype": "PL",
                })
                sno += 1
            total = zero_sum(entries)
            if money(total) != 0:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": tdate, "accode": "ROUND",
                    "amount": money(-total), "control": self.control, "opaccode": "EP", "vtype": "PL",
                })
        log_delpart(self.pe.db, self.session, f"Purchase Return(slno {slno}) Saved", utype="A", ttype="T")
        return {"slno": slno, "lines": len(entries)}
