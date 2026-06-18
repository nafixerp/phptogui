"""Print layouts (reportlab) — base voucher/bill PDF builder.

Mirrors the Blade print layouts at a functional level: a shop header, a title,
a key/value detail block and an optional line-item table, written to a PDF file.
Used by bill/voucher print across modules.
"""

from __future__ import annotations

from decimal import Decimal

try:  # reportlab is optional until a print is actually requested
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    _RL_ERROR = None
except Exception as exc:  # pragma: no cover
    _RL_ERROR = exc


def format_money(value, symbol: str = "₹", places: int = 2) -> str:
    d = value if isinstance(value, Decimal) else Decimal(str(value or 0))
    return f"{symbol}{d:,.{places}f}"


def build_document(path: str, *, title: str, shop: dict, details: list[tuple[str, str]],
                   items: list[dict] | None = None, item_columns: list[tuple[str, str]] | None = None,
                   footer: str = "") -> str:
    """Write a simple bill/voucher PDF to `path` and return the path."""
    if _RL_ERROR is not None:
        raise RuntimeError("reportlab is not installed. Run: pip install reportlab") from _RL_ERROR

    c = canvas.Canvas(path, pagesize=A5)
    w, h = A5
    y = h - 15 * mm

    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2, y, str(shop.get("name") or "")); y -= 6 * mm
    c.setFont("Helvetica", 8)
    for key in ("address", "phone", "gst"):
        val = str(shop.get(key) or "").strip()
        if val:
            c.drawCentredString(w / 2, y, val); y -= 4.5 * mm
    y -= 2 * mm
    c.setLineWidth(0.5); c.line(12 * mm, y, w - 12 * mm, y); y -= 6 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(w / 2, y, title); y -= 7 * mm

    c.setFont("Helvetica", 9)
    for label, value in details:
        c.drawString(14 * mm, y, f"{label}:")
        c.drawString(50 * mm, y, str(value)); y -= 5 * mm

    if items and item_columns:
        y -= 3 * mm
        c.setFont("Helvetica-Bold", 8)
        x_positions = [14 * mm + i * (28 * mm) for i in range(len(item_columns))]
        for (key, head), x in zip(item_columns, x_positions):
            c.drawString(x, y, head)
        y -= 4 * mm
        c.line(12 * mm, y, w - 12 * mm, y); y -= 4 * mm
        c.setFont("Helvetica", 8)
        for it in items:
            for (key, _h), x in zip(item_columns, x_positions):
                c.drawString(x, y, str(it.get(key, "")))
            y -= 4.5 * mm
            if y < 20 * mm:
                c.showPage(); y = h - 20 * mm

    if footer:
        y -= 6 * mm
        c.setFont("Helvetica-Oblique", 8)
        c.drawCentredString(w / 2, y, footer)

    c.showPage()
    c.save()
    return path
