"""Order Sale — port of OrderSaleController (the order→sale conversion).

The single largest screen in the app. This module focuses on the parity-critical
core:

* ``build_entries`` — the daybook head list of
  ``insertLegacyDaybookEntries`` (op account ``RS``): receipt split
  (cash/cc/chq + bank commission), customer debit/credit, the standard charge
  heads (discount/HMC/TCS/repair/advance/fancy/scheme), tax (GST split or VAT),
  AST, and the RS / ESR / EP / VA sales heads — always closed to zero with a
  ROUND balancer.
* ``post`` — reserves the serial + bill number, persists ``salesm``/``salesd``
  (column-filtered), decreases item stock via ``core/stock_adjust``, posts the
  daybook, and marks the source order billed (``orderm.status=2``,
  ``salebill``).

PDC side-records and bank-commission tax are included but, like the secondary
sync, are documented edge paths.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money, weight as wq
from ...core.posting import PostingEngine, zero_sum
from ...core.stock_adjust import adjust_item_stock

_RS = "RS"


def _n(d: dict, *keys) -> Decimal:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return money(d[k])
    return money(0)


class OrderSaleError(Exception):
    pass


class OrderSalePostingService:
    """Daybook head builder + sale posting for the order-sale screen."""

    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.db = engine.db
        self.session = session
        self.control = int(control or 1)

    # -- the parity heart -----------------------------------------------------
    def build_entries(self, a: dict) -> list[dict]:
        entries: list[dict] = []

        def add(accode: str, amount, op: str = _RS) -> None:
            ac = str(accode or "").strip()
            amt = money(amount)
            if not ac or amt == 0:
                return
            entries.append({"accode": ac[:20], "amount": amt, "opaccode": (op or _RS)[:20]})

        cust = str(a.get("customer_code") or "").strip()
        co_party = str(a.get("co_party_code") or "").strip()
        cbcode = str(a.get("cashbank_code") or "").strip()
        if cbcode == "" or cbcode.upper() == "CASH IN HAND":
            cbcode = "CASH"
        chq_bank = str(a.get("chq_bank") or cbcode).strip() or cbcode

        bill_amt = _n(a, "bill_total")
        ex_amt = _n(a, "exchange_amount")
        ret_amt = _n(a, "return_amount")
        disc = _n(a, "discount")
        tax_amt = _n(a, "tax")
        ast_amt = _n(a, "ast")
        tcs_amt = _n(a, "tcs_amt")
        rc_amt = _n(a, "repair_charge")
        adv_amt = _n(a, "advance")
        fancy_amt = _n(a, "fancy_amt")
        scheme_amt = _n(a, "scheme_amt")
        hmc_amt = _n(a, "hallmark_charge")
        net_amt = _n(a, "net_total")
        rcvd = _n(a, "received")
        cc_amt = _n(a, "cc_amt", "ccamt")
        chq_amt = _n(a, "chq_amt", "cheque_amt")
        is_cst = str(a.get("is_cst") or "N").strip().upper() == "Y"
        tax_system = str(a.get("tax_system") or "GST").strip().upper()
        va_sep_ac = str(a.get("va_sep_ac") or "N").strip().upper() == "Y"
        add_bc = str(a.get("add_bank_charge") or "N").strip().upper() == "Y"
        bc_perc = money(a.get("bc_perc") or 0)
        bc_tax_perc = money(a.get("bc_tax_perc") or 0)
        dtva = money(a.get("dtva") or 0)
        og_exchange = bool(a.get("has_og_exchange"))
        linked_order = bool(a.get("linked_order"))

        # Receipt split
        if rcvd != 0:
            if rcvd > (cc_amt + chq_amt) or rcvd < 0:
                dacamt = money(-(rcvd - cc_amt - chq_amt))
                saccode = cbcode if (cbcode != "CASH" and (cc_amt + chq_amt) == 0) else "CASH"
                add(saccode, dacamt)
            if cc_amt > 0:
                add("CNC" if str(a.get("cc_pdc") or "N").upper() == "Y" else cbcode, money(-cc_amt))
            if chq_amt > 0:
                add("CNC" if str(a.get("chq_pdc") or "N").upper() == "Y" else chq_bank, money(-chq_amt))
            if cbcode != "CASH" and bc_perc > 0:
                base = cc_amt if cc_amt > 0 else (money(net_amt - _n(a, "bank_charge")) if add_bc else rcvd)
                dcomn = money(base * bc_perc / 100)
                dcomn_tax = money(dcomn * bc_tax_perc / 100)
                if dcomn != 0:
                    add(cbcode, dcomn)
                    if not add_bc:
                        add("BCOMN", money(-dcomn))
                if dcomn_tax != 0:
                    add(cbcode, dcomn_tax)
                    if not add_bc:
                        add("BCOMNTAX", money(-dcomn_tax))

        # Customer debit / credit
        if cust:
            add(cust, money(-(net_amt - disc)))
            if rcvd != 0:
                add(cust, rcvd)

        # Standard charge heads
        add(str(a.get("sdisc_ac") or "DISC"), money(-disc))
        add("HMC", hmc_amt)
        add("TCSAC", tcs_amt)
        add("RCAMT", rc_amt)
        add(cust if cust else "ADVANCE", money(-adv_amt))
        add("FANCY", fancy_amt)
        if scheme_amt != 0:
            scheme_ac = co_party if co_party else "APP"
            if linked_order and cust:
                scheme_ac = cust
            add(scheme_ac, money(-scheme_amt))

        # Tax heads
        if tax_amt != 0:
            if tax_system == "VAT":
                add(str(a.get("stax_ac") or "TAX"), tax_amt)
            elif is_cst:
                add("IGST", tax_amt)
            else:
                half = money(tax_amt / 2)
                add("SGST", half)
                add("CGST", half)
        add("AST", ast_amt)

        # Sales / exchange / return heads
        if bill_amt != 0:
            base_sales = money(bill_amt - (dtva if va_sep_ac else 0))
            sop = cbcode if rcvd != 0 else (cust if cust else _RS)
            add("RS", base_sales, sop)
        if ret_amt != 0:
            add("ESR", money(-ret_amt))
        if ex_amt != 0:
            add(str(a.get("og_purchase_ac") or "EP") if og_exchange else "EP", money(-ex_amt))
        if va_sep_ac and dtva != 0:
            add("VA", dtva, "RS")

        return entries

    # -- orchestration --------------------------------------------------------
    def post(self, *, amounts: dict, items: list[dict], billdate: str,
             bill_no: str | None = None, order_no: str = "",
             salesm_extra: dict | None = None) -> dict:
        if not self.db.table_exists("daybook"):
            raise OrderSaleError("daybook table not found")
        cust = str(amounts.get("customer_code") or "").strip()
        entries = self.build_entries(amounts)

        with self.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            if not bill_no:
                bill_no = self._bill_number(tx)

            # salesm header (column filtered)
            if self.db.table_exists("salesm"):
                row = {"slno": slno, "billno": bill_no, "tdate": billdate,
                       "custcode": cust, "custname": str(amounts.get("customer_name") or "").strip(),
                       "billamt": _n(amounts, "bill_total"), "netamt": _n(amounts, "net_total"),
                       "discount": _n(amounts, "discount"), "eamt": _n(amounts, "exchange_amount"),
                       "sretamt": _n(amounts, "return_amount"), "orderno": order_no,
                       "control": self.control, "status": 1, "sr": "S"}
                if salesm_extra:
                    row.update(salesm_extra)
                self._insert(tx, "salesm", row)

            # salesd items + stock decrease
            sno = 1
            for it in items:
                code = str(it.get("item_code") or it.get("code") or "").strip().upper()
                if not code:
                    continue
                weight = wq(it.get("weight")); qty = int(it.get("qty") or 0)
                stone = wq(it.get("stonewgt") or it.get("stone_wgt"))
                stktype = str(it.get("stktype") or "").strip()
                if self.db.table_exists("salesd"):
                    self._insert(tx, "salesd", {
                        "slno": slno, "sno": sno, "code": code, "qty": qty, "weight": weight,
                        "stonewgt": stone, "amount": money(it.get("amount")),
                        "mcharge": money(it.get("making_charge") or it.get("mcharge")),
                        "rate": money(it.get("rate")), "stktype": stktype})
                adjust_item_stock(self.db, tx, code, -qty, money(-weight), money(-stone), stktype, self.control)
                sno += 1

            # daybook
            if self.db.table_exists("daybookpart"):
                self.pe.insert_daybookpart(tx, {
                    "slno": slno, "vchno": bill_no,
                    "particular": f"By Order Sales ({bill_no})"[:100]})
            dsno = 1
            for e in entries:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": dsno, "tdate": billdate, "accode": e["accode"],
                    "amount": e["amount"], "control": self.control, "opaccode": e["opaccode"], "vtype": "SL"})
                dsno += 1
            residual = money(zero_sum(entries))
            if residual != 0:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": dsno, "tdate": billdate, "accode": "ROUND",
                    "amount": money(-residual), "control": self.control, "opaccode": "RS", "vtype": "SL"})

            # mark order billed
            order_no = str(order_no).strip().upper()
            if order_no and self.db.table_exists("orderm"):
                if tx.fetchall("SELECT 1 FROM orderm WHERE TRIM(ordno) = :o LIMIT 1", {"o": order_no}):
                    sets = "status = 2"
                    params = {"o": order_no}
                    if self.db.column_exists("orderm", "salebill"):
                        sets += ", salebill = :b"; params["b"] = bill_no
                    tx.execute(f"UPDATE orderm SET {sets} WHERE TRIM(ordno) = :o", params)

        log_delpart(self.db, self.session, f"Order Sale({bill_no}) Posted", utype="A", ttype="R")
        return {"slno": slno, "bill_no": bill_no, "balanced": residual == 0, "lines": len(entries)}

    def _bill_number(self, tx) -> str:
        prefix = "SLB/"
        if self.db.table_exists("generals"):
            p = tx.scalar("SELECT cvalue FROM generals WHERE code = 'SBPREF'")
            if p and str(p).strip():
                prefix = str(p).strip()
        nxt = self.pe.increment_gen_int(tx, "SALESB")
        return f"{prefix}{nxt:05d}"

    def _insert(self, tx, table: str, row: dict) -> None:
        cols = set(self.db.columns(table))
        use = {k: v for k, v in row.items() if k in cols}
        if not use:
            return
        names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
        tx.execute(f"INSERT INTO {table} ({names}) VALUES ({binds})", use)
