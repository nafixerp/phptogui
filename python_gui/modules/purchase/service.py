"""Purchase posting — port of PurchaseBillController::writePurchaseDaybook.

Entry order (opaccode='EP' for all except the EP purchase credit, vtype='PL'):
  CASH +cashPaid · CNP/chqBank +chqAmt · EP +exchAmt · supplier +(net+others) ·
  supplier -paidAmt · ADD -others · HMC -hmc · TCSAC -tcs · PDISCAC +discount ·
  SGST/CGST -tax/2 (or IGST -tax, or PTAXEXP -tax if external) · EP -billTotal ·
  ROUND -roundAmt · ROUND -residual  => sums to zero.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum


class PurchaseError(Exception):
    pass


def _n(amounts: dict, key: str) -> Decimal:
    return money(amounts.get(key, 0))


class PurchasePostingService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def build_entries(self, amounts: dict) -> list[dict]:
        EP = "EP"
        entries: list[dict] = []

        def ins(accode: str, amount: Decimal, opacc: str) -> None:
            amt = money(amount)
            if amt == 0:
                return
            entries.append({"accode": str(accode or "")[:20], "amount": amt, "opaccode": opacc[:20]})

        supp = str(amounts.get("supplier_code") or "").strip()
        chq_bank = str(amounts.get("chq_bank") or "").strip()
        chq_pdc = str(amounts.get("chq_pdc") or "N").strip().upper()
        disc_ac = self.pe.general_profile("PDISCAC", "DISC") or "DISC"
        interstate = bool(amounts.get("interstate"))
        tax_ext = bool(amounts.get("tax_ext"))

        bill_total = _n(amounts, "bill_total")
        net_total = _n(amounts, "net_total")
        exch = _n(amounts, "exchange_amount")
        paid = _n(amounts, "paid_amount")
        chq = _n(amounts, "chq_amount")
        disc = _n(amounts, "discount")
        tax = _n(amounts, "tax")
        cess = _n(amounts, "cess")
        hmc = _n(amounts, "hallmark_charge")
        tcs = _n(amounts, "tcs_amt")
        roundamt = _n(amounts, "round_amt")
        others = _n(amounts, "others")

        dacamt = money(net_total + others)
        cash_paid = money(paid - chq)

        if cash_paid > 0:
            ins("CASH", cash_paid, EP)
        if chq > 0:
            cb = "CNP" if chq_pdc == "Y" else (chq_bank or "CASH")
            ins(cb, chq, EP)
        if exch > 0:
            ins(EP, exch, EP)
        if dacamt != 0:
            ins(supp or EP, dacamt, EP)
        if paid > 0:
            ins(supp or EP, money(-paid), EP)
        if others > 0:
            ins("ADD", money(-others), EP)
        if hmc > 0:
            ins("HMC", money(-hmc), EP)
        if tcs > 0:
            ins("TCSAC", money(-tcs), EP)
        if disc > 0:
            ins(disc_ac, disc, EP)

        total_tax = money(tax + cess)
        if total_tax > 0:
            if tax_ext:
                ins("PTAXEXP", money(-total_tax), EP)
            elif interstate:
                ins("IGST", money(-total_tax), EP)
            else:
                half = money(total_tax / 2)
                ins("SGST", money(-half), EP)
                ins("CGST", money(-half), EP)

        if bill_total > 0:
            if cash_paid > 0:
                ep_op = "CASH"
            elif chq > 0:
                ep_op = chq_bank or "CASH"
            elif supp != "":
                ep_op = supp
            else:
                ep_op = EP
            ins(EP, money(-bill_total), ep_op)

        if roundamt != 0:
            ins("ROUND", money(-roundamt), EP)

        return entries

    def post(self, slno: int, billdate: str, amounts: dict) -> dict:
        if not self.pe.db.table_exists("daybook"):
            raise PurchaseError("daybook table not found")
        entries = self.build_entries(amounts)
        sno = 1
        with self.pe.db.transaction() as tx:
            if not slno or int(slno) <= 0:
                slno = self.pe.next_serial_no(tx)
            if self.pe.db.table_exists("daybookpart"):
                self.pe.insert_daybookpart(tx, {
                    "slno": slno, "tdate": billdate, "control": self.control,
                    "particular": str(amounts.get("particular") or f"By Purchase {slno}")[:200],
                    "vchno": str(slno),
                })
            for e in entries:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": billdate, "accode": e["accode"],
                    "amount": e["amount"], "control": self.control, "opaccode": e["opaccode"],
                    "vtype": "PL",
                })
                sno += 1
            total = zero_sum(entries)
            if money(total) != 0:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": billdate, "accode": "ROUND",
                    "amount": money(-total), "control": self.control, "opaccode": "EP", "vtype": "PL",
                })
        log_delpart(self.pe.db, self.session, f"Purchase(slno {slno}) Posted", utype="A", ttype="R")
        return {"slno": slno, "lines": len(entries)}
