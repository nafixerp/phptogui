"""Sales posting — port of SalesBillController's daybook entry builder.

Reproduces the ledger side of a sales bill (vtype = SL): the receipt split,
customer debit/credit pair, charge heads, tax heads (SGST/CGST/IGST or STAXAC),
sales-return reversal, exchange (EP), value-addition (VA), and the RS sales head,
followed by a ROUND row that balances the transaction to zero.

The item-level amount computation (per-line VA/wastage/MC/tax) that produces the
`amounts` totals lives in the controller's calc layer; this service accepts those
computed totals (the desktop sales form supplies them) and focuses on the
parity-critical posting. Deferred (documented): bank-commission (BCOMN) split and
PDC list rows.

Source: SalesBillController::<daybook builder> (lines ~2630-2935).
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum


class SalesError(Exception):
    pass


def _n(amounts: dict, key: str) -> Decimal:
    return money(amounts.get(key, 0))


class SalesPostingService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def build_entries(self, amounts: dict, items: list[dict] | None = None,
                      exchange: list[dict] | None = None) -> list[dict]:
        items = items or []
        exchange = exchange or []
        op = "RS"
        entries: list[dict] = []

        def add(accode: str, amount: Decimal, opacc: str = "") -> None:
            ac = str(accode or "").strip()
            amt = money(amount)
            if ac == "" or amt == 0:
                return
            entries.append({"accode": ac, "amount": amt, "opaccode": opacc or op})

        cbcode = str(amounts.get("cashbank_code") or "").strip()
        if cbcode == "" or cbcode.upper() == "CASH IN HAND":
            cbcode = "CASH"
        cust = str(amounts.get("customer_code") or "").strip()
        tax_system = str(amounts.get("tax_system", "GST")).strip().upper()
        is_cst = bool(amounts.get("is_cst"))
        va_sep = bool(amounts.get("va_sep_ac"))

        net = _n(amounts, "net_total")
        bill = _n(amounts, "bill_total")
        ex = _n(amounts, "exchange_amount")
        ret = _n(amounts, "return_amount")
        disc = _n(amounts, "discount")
        tax = _n(amounts, "tax")
        sgst = _n(amounts, "sgst")
        cgst = _n(amounts, "cgst")
        igst = _n(amounts, "igst")
        ast = _n(amounts, "ast")
        tcs = _n(amounts, "tcs_amt")
        rc = _n(amounts, "repair_charge")
        adv = _n(amounts, "advance")
        fancy = _n(amounts, "fancy_amt")
        hmc = _n(amounts, "hallmark_charge")
        scheme = _n(amounts, "scheme_amt")
        scheme_ledger = str(amounts.get("scheme_ledger", "APP")).strip().upper() or "APP"
        if scheme_ledger not in ("APP", "SCHMAMT"):
            scheme_ledger = "APP"
        ptax = _n(amounts, "ptax")
        sr_tax = _n(amounts, "sr_tax_amt")
        sr_cess = _n(amounts, "sr_cess_amt")
        rcvd = _n(amounts, "received")
        cc = _n(amounts, "cc_amt")
        chq = _n(amounts, "chq_amt")

        # value-addition total from items (making_charge + wastage*rate)
        dtva = Decimal("0")
        for it in items:
            dtva += money(it.get("making_charge", 0)) + money(it.get("wastage", 0)) * money(it.get("rate", 0))
        dtva = money(dtva)

        has_og = any(str(r.get("item_code") or "").strip().upper() == "OG" for r in exchange)

        # Receipt split (cash/bank/cc/chq)
        if rcvd != 0:
            if rcvd > (cc + chq) or rcvd < 0:
                dacamt = money(-(rcvd - cc - chq))
                saccode = cbcode if (cbcode != "CASH" and (cc + chq) == 0) else "CASH"
                add(saccode, dacamt)
            if cc > 0:
                add("CNC" if amounts.get("cc_pdc") else cbcode, money(-cc))
            if chq > 0:
                add("CNC" if amounts.get("chq_pdc") else (amounts.get("chq_bank") or cbcode), money(-chq))

        # Customer debit/credit pair
        if cust != "":
            add(cust, money(-(net - disc)))
            if rcvd != 0:
                add(cust, rcvd)

        # Standard charge heads
        add(self.pe.general_profile("SDISCAC", "DISC"), money(-disc))
        add("HMC", hmc)
        add("TCSAC", tcs)
        add("RCAMT", rc)
        add(cust if cust != "" else "ADVANCE", money(-adv))
        add("FANCY", fancy)
        if scheme != 0:
            add(scheme_ledger, money(-scheme))

        # Tax heads
        if tax != 0:
            if tax_system == "VAT":
                add(self.pe.general_profile("STAXAC", "TAX"), tax)
            elif is_cst:
                add("IGST", igst if igst != 0 else tax)
            else:
                add("SGST", sgst)
                add("CGST", cgst)
        add("AST", ast)

        if ret != 0:
            if sr_tax != 0:
                if tax_system == "VAT":
                    add(self.pe.general_profile("STAXAC", "TAX"), money(-sr_tax))
                elif is_cst:
                    add("IGST", money(-sr_tax))
                else:
                    add("SGST", money(-sr_tax / 2))
                    add("CGST", money(-sr_tax / 2))
            add("AST", money(-sr_cess))

        if ptax != 0:
            add(self.pe.general_profile("PTAXAC", "PTAX"), money(-ptax))
            add("PTAXEXP", ptax)

        # Sales / Return / Exchange / VA heads
        if bill != 0:
            base_sales = money(bill - (dtva if va_sep else Decimal("0")))
            sop = cbcode if rcvd != 0 else (cust if cust != "" else op)
            add("RS", base_sales, sop)
        if ret != 0:
            add("ESR", money(-(ret - sr_tax - sr_cess)))
        if ex != 0:
            add("EP" if not has_og else str(amounts.get("og_purchase_ac", "EP")), money(-ex))
        if va_sep and dtva != 0:
            add("VA", dtva, "RS")

        return entries

    def post(self, slno: int, billdate: str, amounts: dict,
             items: list[dict] | None = None, exchange: list[dict] | None = None) -> dict:
        if not self.pe.db.table_exists("daybook"):
            raise SalesError("daybook table not found")
        entries = self.build_entries(amounts, items, exchange)
        sno = 1
        with self.pe.db.transaction() as tx:
            if not slno or int(slno) <= 0:
                slno = self.pe.next_serial_no(tx)
            for e in entries:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": billdate, "accode": e["accode"][:20],
                    "amount": e["amount"], "control": self.control,
                    "opaccode": (e["opaccode"] or "RS")[:20], "vtype": "SL",
                })
                sno += 1
            total = zero_sum(entries)
            if money(total) != 0:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": billdate, "accode": "ROUND",
                    "amount": money(-total), "control": self.control, "opaccode": "RS", "vtype": "SL",
                })
        log_delpart(self.pe.db, self.session, f"Sales(slno {slno}) Posted", utype="A", ttype="R")
        return {"slno": slno, "lines": len(entries)}
