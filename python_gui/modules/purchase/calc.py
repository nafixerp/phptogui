"""Purchase bill computation — line amount + totals for PurchasePostingService.

Mirrors the sales line amount (netWgt*rate + MC + stone) and aggregates a bill
total + GST tax (exclusive) + net total, producing the `amounts` dict the
purchase posting consumes. Decimal throughout.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from ...core.decimals import to_decimal


def _d(v) -> Decimal:
    return to_decimal(v) or Decimal("0")


def _r(v, p: int = 2) -> Decimal:
    q = Decimal("1") if p == 0 else Decimal("0.01")
    return _d(v).quantize(q, rounding=ROUND_HALF_UP)


def line_amount(item: dict) -> Decimal:
    qty = _d(item.get("qty", 0))
    weight = _d(item.get("weight", 0))
    stone_wgt = _d(item.get("stone_wgt", 0))
    net_wgt = weight - stone_wgt
    rate = _d(item.get("rate", 0))
    mc = _d(item.get("making_charge", item.get("mc", 0)))
    stone = _d(item.get("stone_price", 0))
    stkinnos = str(item.get("stkinnos") or "N").strip().upper() == "Y"
    base = (qty * rate) if stkinnos else (net_wgt * rate)
    return _r(base + mc + stone)


def compute(items: list[dict], extra: dict | None = None) -> dict:
    extra = dict(extra or {})
    bill_total = Decimal("0")
    for it in items:
        bill_total += _d(it.get("amount", line_amount(it)))
    bill_total = _r(bill_total)

    interstate = bool(extra.get("interstate"))
    tax_perc = _d(extra.get("tax_perc", 0))
    tax = _r(extra.get("tax", 0))
    if tax_perc > 0:
        tax = _r(bill_total * tax_perc / 100)

    others = _d(extra.get("others", 0))
    hmc = _d(extra.get("hallmark_charge", 0))
    tcs = _d(extra.get("tcs_amt", 0))
    disc = _d(extra.get("discount", 0))
    exch = _d(extra.get("exchange_amount", 0))
    net_total = _r(bill_total + tax + others + hmc + tcs - disc - exch)

    return {
        "supplier_code": extra.get("supplier_code", ""), "bill_total": bill_total,
        "net_total": net_total, "tax": tax, "cess": _r(extra.get("cess", 0)),
        "interstate": interstate, "tax_ext": bool(extra.get("tax_ext")),
        "discount": _r(disc), "others": _r(others), "hallmark_charge": _r(hmc),
        "tcs_amt": _r(tcs), "exchange_amount": _r(exch),
        "paid_amount": _r(extra.get("paid_amount", 0)), "chq_amount": _r(extra.get("chq_amount", 0)),
        "chq_bank": extra.get("chq_bank", ""), "round_amt": _r(extra.get("round_amt", 0)),
    }
