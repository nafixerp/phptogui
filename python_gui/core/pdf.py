"""Print-layout base (reportlab).

Stub for Phase 1 — bill/report layouts are ported per-module to match the Blade
print views (app/Support/PrintLayout.php). Centralised here so every module
shares the same page setup, fonts and currency formatting.
"""

from __future__ import annotations

from decimal import Decimal


def format_money(value: Decimal, symbol: str = "₹", places: int = 2) -> str:
    return f"{symbol}{value:,.{places}f}"


def build_document(*args, **kwargs):  # pragma: no cover - implemented per report
    raise NotImplementedError(
        "PDF rendering is added when the first printable module (Phase 5) is ported."
    )
