"""Sales Return + Purchase Return posting — zero-sum + correct heads."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine, zero_sum
from python_gui.modules.purchase_return.service import PurchaseReturnService
from python_gui.modules.sales_return.service import SalesReturnService

sqlite3.register_adapter(Decimal, str)
_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode", "vtype"}
_DP = {"slno", "vchno", "particular", "tdate", "control"}


def make_pe():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT, vtype TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, tdate TEXT, control INT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    pe.db.table_exists = lambda t: t in ("daybook", "daybookpart", "generali")
    pe.db.column_exists = lambda t, c: True
    pe.db.columns = lambda t: _DB if t == "daybook" else _DP if t == "daybookpart" else set()
    return db, pe


def rows(db, slno):
    return db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno = :s ORDER BY sno", {"s": slno})


def test_sales_return_balances_and_heads():
    db, pe = make_pe()
    res = SalesReturnService(pe).post(0, "2026-06-17", {
        "billno": "SR1", "custcode": "C0001", "cbcode": "CASH",
        "billamt": "10000", "staxamt": "300", "discount": "100", "pamt": "0"})
    r = rows(db, res["slno"])
    by = {x["accode"]: Decimal(str(x["amount"])) for x in r}
    # customer +(10000+300-100)=10200 ; SGST/CGST -150 each ; DISC +100 ; ESR -10000
    assert by["C0001"] == Decimal("10200.00")
    assert by["SGST"] == Decimal("-150.00") and by["CGST"] == Decimal("-150.00")
    assert by["DISC"] == Decimal("100.00") and by["ESR"] == Decimal("-10000.00")
    assert zero_sum(r) == Decimal("0.00")
    assert all(x["opaccode"] == "ESR" for x in r)


def test_sales_return_with_cash_refund_balances():
    db, pe = make_pe()
    res = SalesReturnService(pe).post(0, "2026-06-17", {
        "billno": "SR2", "custcode": "C0001", "cbcode": "CASH",
        "billamt": "5000", "staxamt": "0", "discount": "0", "pamt": "5000"})
    r = rows(db, res["slno"])
    assert zero_sum(r) == Decimal("0.00")
    by = {}
    for x in r:
        by.setdefault(x["accode"], Decimal("0")); by[x["accode"]] += Decimal(str(x["amount"]))
    assert by["CASH"] == Decimal("5000.00")     # refund out
    assert by["C0001"] == Decimal("0.00")       # +5000 owed back, -5000 paid


def test_purchase_return_balances_and_heads():
    db, pe = make_pe()
    res = PurchaseReturnService(pe).post(0, "2026-06-17", {
        "suppcode": "S0001", "bill_total": "10000", "net_total": "10500", "paid_amount": "10500", "tax": "500"})
    r = rows(db, res["slno"])
    by = {}
    for x in r:
        by.setdefault(x["accode"], Decimal("0")); by[x["accode"]] += Decimal(str(x["amount"]))
    assert by["EP"] == Decimal("10000.00")          # purchase account debited (return)
    assert by["CASH"] == Decimal("-10500.00")       # cash received back
    assert by["SGST"] == Decimal("250.00") and by["CGST"] == Decimal("250.00")
    assert by["S0001"] == Decimal("0.00")           # -dacamt then +paid
    assert zero_sum(r) == Decimal("0.00")


def test_purchase_return_interstate_igst():
    db, pe = make_pe()
    res = PurchaseReturnService(pe).post(0, "2026-06-17", {
        "suppcode": "S1", "bill_total": "1000", "net_total": "1180", "paid_amount": "1180",
        "tax": "180", "interstate": True})
    by = {x["accode"]: Decimal(str(x["amount"])) for x in rows(db, res["slno"])}
    assert by.get("IGST") == Decimal("180.00")
    assert zero_sum(rows(db, res["slno"])) == Decimal("0.00")
