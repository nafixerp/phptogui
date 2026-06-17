"""Decimal helpers for money and weight.

HARD RULE: money and weight are decimals, never floats. The MySQL schema is
frozen, so values must round to the same scale the columns use. Jewellery
amounts are typically DECIMAL(.,2) and weights DECIMAL(.,3); the exact scale is
applied per-module from the column definition when we port that module.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Common quantisers (override per-column when the real scale differs).
MONEY = Decimal("0.01")
WEIGHT = Decimal("0.001")
RATE = Decimal("0.01")


def to_decimal(value, default: Decimal | None = Decimal("0")) -> Decimal | None:
    """Coerce DB/UI input to Decimal without going through float."""
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # Guard against float drift sneaking in: route via str.
        value = repr(value)
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return default


def quantize(value, places: Decimal) -> Decimal:
    d = to_decimal(value) or Decimal("0")
    return d.quantize(places, rounding=ROUND_HALF_UP)


def money(value) -> Decimal:
    return quantize(value, MONEY)


def weight(value) -> Decimal:
    return quantize(value, WEIGHT)
