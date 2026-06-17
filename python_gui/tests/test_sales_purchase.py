"""Sales & Purchase posting — zero-sum invariant + correct heads/signs."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine, zero_sum
from python_gui.modules.purchase.service import PurchasePostingService
from python_gui.modules.sales.service import SalesPostingService

sqlite3.register_adapter(Decimal, str)
_DB_COLS = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode", "vtype", "note"}
_DP_COLS = {"slno", "vchno", "particular", "tdate", "control", "vtype"}


def make_engine():
    db = Database()
    db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT, vtype TEXT, note TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, tdate TEXT, control INT, vtype TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE generals (code TEXT PRIMARY KEY, cvalue TEXT)"))
    pe = PostingEngine(db)
    pe.db.table_exists = lambda t: t in ("daybook", "daybookpart", "generali", "generals")
    pe.db.column_exists = lambda t, c: (c in _DB_COLS) if t == "daybook" else (c in _DP_COLS) if t == "daybookpart" else True
    pe.db.columns = lambda t: _DB_COLS if t == "daybook" else _DP_COLS if t == "daybookpart" else set()
    return db, pe


def lines(db, slno):
    return db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno = :s ORDER BY sno", {"s": slno})


# -- Sales -------------------------------------------------------------------

def test_sales_cash_with_tax_balances():
    db, pe = make_engine()
    res = SalesPostingService(pe).post(0, "2026-06-17", {
        "customer_code": "", "cashbank_code": "CASH",
        "bill_total": "10000", "net_total": "10500", "tax": "500",
        "sgst": "250", "cgst": "250", "received": "10500",
    })
    rows = lines(db, res["slno"])
    assert zero_sum(rows) == Decimal("0.00")           # ROUND-balanced to zero
    by = {r["accode"]: Decimal(str(r["amount"])) for r in rows}
    assert by["RS"] == Decimal("10000.00")
    assert by["SGST"] == Decimal("250.00") and by["CGST"] == Decimal("250.00")
    assert by["CASH"] == Decimal("-10500.00")          # received into cash


def test_sales_credit_customer_with_discount():
    db, pe = make_engine()
    res = SalesPostingService(pe).post(0, "2026-06-17", {
        "customer_code": "C0001", "cashbank_code": "CASH",
        "bill_total": "5000", "net_total": "5000", "discount": "100",
    })
    rows = lines(db, res["slno"])
    by = {r["accode"]: Decimal(str(r["amount"])) for r in rows}
    assert by["C0001"] == Decimal("-4900.00")          # -(net - disc)
    assert by["DISC"] == Decimal("-100.00")
    assert by["RS"] == Decimal("5000.00")
    assert zero_sum(rows) == Decimal("0.00")


def test_sales_interstate_uses_igst():
    db, pe = make_engine()
    res = SalesPostingService(pe).post(0, "2026-06-17", {
        "customer_code": "C0001", "cashbank_code": "CASH",
        "bill_total": "1000", "net_total": "1180", "tax": "180", "igst": "180", "is_cst": True,
    })
    by = {r["accode"]: Decimal(str(r["amount"])) for r in lines(db, res["slno"])}
    assert by["IGST"] == Decimal("180.00") and "SGST" not in by
    assert zero_sum(lines(db, res["slno"])) == Decimal("0.00")


# -- Purchase ----------------------------------------------------------------

def test_purchase_cash_balances_and_heads():
    db, pe = make_engine()
    res = PurchasePostingService(pe).post(0, "2026-06-17", {
        "supplier_code": "S0001", "bill_total": "10000", "net_total": "10500",
        "paid_amount": "10500", "tax": "500",
    })
    rows = lines(db, res["slno"])
    by = {}
    for r in rows:                                     # EP appears twice (+/-)
        by.setdefault(r["accode"], Decimal("0"))
        by[r["accode"]] += Decimal(str(r["amount"]))
    assert by["CASH"] == Decimal("10500.00")           # cash paid (debit-side positive)
    assert by["EP"] == Decimal("-10000.00")            # purchase account credit
    assert by["SGST"] == Decimal("-250.00") and by["CGST"] == Decimal("-250.00")
    assert by["S0001"] == Decimal("0.00")              # owed (+net+others) then paid (-paid)
    assert zero_sum(rows) == Decimal("0.00")


def test_purchase_interstate_and_external_tax():
    db, pe = make_engine()
    inter = PurchasePostingService(pe).post(0, "2026-06-17", {
        "supplier_code": "S0001", "bill_total": "1000", "net_total": "1180",
        "paid_amount": "1180", "tax": "180", "interstate": True})
    by = {r["accode"]: Decimal(str(r["amount"])) for r in lines(db, inter["slno"])}
    assert by.get("IGST") == Decimal("-180.00")

    ext = PurchasePostingService(pe).post(0, "2026-06-17", {
        "supplier_code": "S0002", "bill_total": "1000", "net_total": "1180",
        "paid_amount": "1180", "tax": "180", "tax_ext": True})
    rows = lines(db, ext["slno"])
    by2 = {r["accode"]: Decimal(str(r["amount"])) for r in rows}
    assert by2.get("PTAXEXP") == Decimal("-180.00")
    assert zero_sum(rows) == Decimal("0.00")
