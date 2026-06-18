"""Sales bill computation — port of SalesBillController::calcTotals + line amount.

Turns the item grid + charges into the `amounts` dict that SalesPostingService
consumes, computing: per-line amount, bill total (with tax-inclusive items),
discount, GST tax (+ SGST/CGST/IGST split), cess, exchange/return offsets, TCS,
hallmark/repair/advance/fancy/scheme, round-off, net total and received.

All money is Decimal. Rounding matches the controller (2 dp, or 0 dp when
round_to == 1; TCS and received round to whole units).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from ...core.decimals import money, to_decimal


def _d(v) -> Decimal:
    return to_decimal(v) or Decimal("0")


def _round(v: Decimal, places: int = 2) -> Decimal:
    q = Decimal("1") if places == 0 else Decimal("0.01")
    return _d(v).quantize(q, rounding=ROUND_HALF_UP)


def line_amount(item: dict) -> Decimal:
    """Per-item amount: (netWgt*rate)+stone+mc+dmd, or qty*rate when stkinnos."""
    qty = _d(item.get("qty", 0))
    weight = _d(item.get("weight", 0))
    stone_wgt = _d(item.get("stone_wgt", item.get("stonewgt", 0)))
    net_wgt = weight - stone_wgt
    rate = _d(item.get("rate", 0))
    stone_price = _d(item.get("stone_price", item.get("stoneprice", 0)))
    mc = _d(item.get("making_charge", item.get("mc", 0)))
    dmd = _d(item.get("dmdamt", item.get("dmd_amt", 0)))
    stkinnos = str(item.get("stkinnos") or "N").strip().upper() == "Y"
    base = (qty * rate) if stkinnos else (net_wgt * rate)
    return _round(base + stone_price + mc + dmd)


def tax_split(tax_amount, is_cst: bool) -> dict:
    """Port of salesTaxSplitFromAmount()."""
    tax = _round(tax_amount)
    if is_cst:
        return {"sgst": Decimal("0"), "cgst": Decimal("0"), "igst": tax}
    cgst = _round(tax / 2)
    sgst = _round(tax - cgst)
    return {"sgst": sgst, "cgst": cgst, "igst": Decimal("0")}


def compute(items: list[dict], exchange: list[dict] | None = None,
            sales_return: list[dict] | None = None, extra: dict | None = None) -> dict:
    """Port of calcTotals(). Returns the `amounts` dict for SalesPostingService."""
    exchange = exchange or []
    sales_return = sales_return or []
    extra = dict(extra or {})

    is_cst = bool(extra.get("is_cst"))
    tax_perc = _d(extra.get("tax_perc", 0))
    ast_perc = Decimal("0") if is_cst else _d(extra.get("ast_perc", extra.get("cess_perc", 0)))
    inclusive_rate = tax_perc + ast_perc

    inclusive_base = Decimal("0")
    inclusive_tax = Decimal("0")
    inclusive_ast = Decimal("0")
    exclusive_base = Decimal("0")
    for row in items:
        amount = _d(row.get("amount", line_amount(row)))
        tax_internal = str(row.get("taxinternal", row.get("tax_internal", "")) or "").strip().upper() in ("Y", "1", "TRUE") \
            or row.get("taxinternal") is True or row.get("tax_internal") is True
        if tax_internal and inclusive_rate > 0:
            base = (amount * 100) / (100 + inclusive_rate)
            included = amount - base
            inclusive_base += base
            inclusive_tax += included * (tax_perc / inclusive_rate)
            inclusive_ast += included * (ast_perc / inclusive_rate)
        else:
            exclusive_base += amount

    bill_total = _round(exclusive_base + inclusive_base)
    exchange_amount = _round(sum((_d(r.get("amount", 0)) for r in exchange), Decimal("0")))
    sr_tax = _d(extra.get("sr_tax_amt", 0))
    sr_cess = _d(extra.get("sr_cess_amt", 0))
    sr_disc = _d(extra.get("sr_discount_amt", 0))
    return_amount = _round(sum((_d(r.get("amount", 0)) for r in sales_return), Decimal("0")) - sr_disc + sr_tax + sr_cess)

    discount = _d(extra.get("discount", 0))
    discount_perc = _d(extra.get("discount_perc", 0))
    if discount == 0 and discount_perc > 0:
        discount = _round(bill_total * discount_perc / 100)
    elif bill_total > 0 and discount > 0 and discount_perc == 0:
        discount_perc = _round(discount * 100 / bill_total, 2)

    tax = _d(extra.get("tax", 0))
    ast = _d(extra.get("ast", extra.get("cess", 0)))
    if tax_perc > 0 or inclusive_tax > 0:
        tax = _round(inclusive_tax + (exclusive_base * tax_perc / 100))
    if ast_perc > 0 or inclusive_ast > 0:
        ast = _round(inclusive_ast + (exclusive_base * ast_perc / 100))

    rc = _d(extra.get("repair_charge", 0))
    hmc = _d(extra.get("hallmark_charge", 0))
    advance = _d(extra.get("advance", 0))
    fancy = _d(extra.get("fancy_amt", 0))
    scheme = _d(extra.get("scheme_amt", 0))
    scheme_ledger = str(extra.get("scheme_ledger", "APP")).strip().upper()
    scheme_ledger = "SCHMAMT" if scheme_ledger == "SCHMAMT" else "APP"
    bank_charge = _d(extra.get("bank_charge", 0))
    add_bank_charge = bool(extra.get("add_bank_charge"))
    opening_bal = _d(extra.get("opening_balance", 0))
    round_mode = int(_d(extra.get("round_to", 0)))
    tcs_perc = _d(extra.get("tcs_perc", 0))

    net_before_tcs = (bill_total + tax + ast + rc + hmc - exchange_amount - return_amount
                      - advance + fancy - scheme)
    if add_bank_charge:
        net_before_tcs += bank_charge
    net_before_tcs = _round(net_before_tcs, 0 if round_mode == 1 else 2)

    tcs_amt = _round((net_before_tcs - discount) * tcs_perc / 100, 0)
    net_total = _round(net_before_tcs + tcs_amt, 0 if round_mode == 1 else 2)
    net_amt = net_total - discount
    grand_amt = opening_bal + net_amt

    credit = bool(extra.get("credit"))
    rcvd = _d(extra.get("received", 0))
    if bool(extra.get("auto_rcvd")) and not credit:
        rcvd = grand_amt if bool(extra.get("grand_to_rcvd")) else net_amt
    rcvd = _round(rcvd, 0)

    split = tax_split(tax, is_cst)
    return {
        "customer_code": extra.get("customer_code", ""), "cashbank_code": extra.get("cashbank_code", "CASH"),
        "tax_system": str(extra.get("tax_system", "GST")), "is_cst": is_cst,
        "va_sep_ac": bool(extra.get("va_sep_ac")),
        "bill_total": bill_total, "net_total": net_total,
        "exchange_amount": exchange_amount, "return_amount": return_amount,
        "discount": _round(discount), "tax": _round(tax),
        "sgst": split["sgst"], "cgst": split["cgst"], "igst": split["igst"],
        "ast": _round(ast), "tcs_amt": _round(tcs_amt), "repair_charge": _round(rc),
        "hallmark_charge": _round(hmc), "advance": _round(advance), "fancy_amt": _round(fancy),
        "scheme_amt": _round(scheme), "scheme_ledger": scheme_ledger,
        "sr_tax_amt": _round(sr_tax), "sr_cess_amt": _round(sr_cess),
        "received": _round(rcvd), "net_amt": _round(net_amt), "grand_amt": _round(grand_amt),
    }
