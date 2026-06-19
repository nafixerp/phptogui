"""Shared helpers for bill/voucher print services (Bucket C prints).

The Laravel print controllers gather the same supporting data — shop/company
info from the ``generals`` table, customer/supplier info from ``clients``,
salesman + state names, and a GST split into CGST/SGST/IGST — before handing it
to a Blade template. These helpers port that gathering + the tax-split maths so
each print service stays small and focused on its own document shape.

Money is kept as :class:`~decimal.Decimal` (HARD RULE 3); the GST split mirrors
the controllers' ``round(..., 2/3)`` behaviour exactly.
"""

from __future__ import annotations

from decimal import Decimal

from .db import Database
from .decimals import money, quantize, to_decimal

# generals codes carrying shop identity (SalesBill/SalesReturn/PurchaseBillPrint).
_SHOP_CODES = ["SHOPNM", "SHOPADDR", "SHOPPHONE", "SHOPGSTIN", "GSTIN"]


def company_info(db: Database) -> dict:
    """Shop header from the ``generals`` table (name/address/phone/gst)."""
    info = {"name": "", "address": "", "phone": "", "gst": ""}
    if not db.table_exists("generals"):
        return info
    ph = ", ".join(f":c{i}" for i in range(len(_SHOP_CODES)))
    rows = db.fetchall(
        f"SELECT code, cvalue FROM generals WHERE code IN ({ph})",
        {f"c{i}": v for i, v in enumerate(_SHOP_CODES)})
    for r in rows:
        code = str(r.get("code") or "").strip().upper()
        val = str(r.get("cvalue") or "").strip()
        if not val:
            continue
        if code == "SHOPNM":
            info["name"] = val
        elif code == "SHOPADDR":
            info["address"] = val
        elif code == "SHOPPHONE":
            info["phone"] = val
        elif code in ("SHOPGSTIN", "GSTIN") and not info["gst"]:
            info["gst"] = val
    return info


def party_info(db: Database, code: str) -> dict:
    """Customer/supplier card from ``clients`` (empty dict if absent)."""
    code = str(code or "").strip()
    if not code or not db.table_exists("clients"):
        return {}
    row = db.fetchone("SELECT * FROM clients WHERE TRIM(code) = :c", {"c": code})
    return dict(row) if row else {}


def lookup_name(db: Database, table: str, code: str, name_col: str = "name") -> str:
    code = str(code or "").strip()
    if not code or not db.table_exists(table) or not db.column_exists(table, name_col):
        return ""
    val = db.scalar(f"SELECT {name_col} FROM {table} WHERE TRIM(code) = :c", {"c": code})
    return str(val or "").strip()


def address_line(party: dict) -> str:
    """Join non-empty addr1/addr2/addr3/city into a single line."""
    parts = [str(party.get(k) or "").strip() for k in ("addr1", "addr2", "addr3", "city")]
    return ", ".join(p for p in parts if p)


def gst_split(tax_amt, tax_perc, cst: str, base_amt=0, net_amt=0) -> dict:
    """Split a sales tax amount into CGST/SGST or IGST.

    Faithful port of SalesBill/SalesReturnPrint: derive the effective rate when
    only the amount is stored, then split intra-state (CGST+SGST, half each) or
    inter-state (IGST, full) based on the ``cst`` flag.
    """
    tax_amt = money(tax_amt)
    eff = to_decimal(tax_perc)
    if eff <= 0 and tax_amt > 0:
        base = to_decimal(base_amt)
        if base <= 0:
            base = max(to_decimal(net_amt) - tax_amt, Decimal("0"))
        if base > 0:
            eff = quantize(tax_amt * 100 / base, Decimal("0.001"))
    if str(cst or "N").strip().upper() == "Y":
        return {"is_igst": True, "eff_perc": eff,
                "igst_label": f"IGST ({eff:.1f}%)", "igst": tax_amt,
                "cgst_label": "", "sgst_label": "", "cgst": money(0), "sgst": money(0)}
    half = quantize(eff / 2, Decimal("0.001"))
    h = money(tax_amt / 2)
    return {"is_igst": False, "eff_perc": eff,
            "cgst_label": f"CGST ({half:.1f}%)", "sgst_label": f"SGST ({half:.1f}%)",
            "cgst": h, "sgst": h, "igst_label": "", "igst": money(0)}


def sum_columns(rows: list[dict], mapping: dict[str, str]) -> dict:
    """Sum a set of detail columns into named totals (Decimal)."""
    out = {k: Decimal("0") for k in mapping}
    for r in rows:
        for out_key, col in mapping.items():
            out[out_key] += to_decimal(r.get(col))
    return out
