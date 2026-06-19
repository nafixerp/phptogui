"""Bucket B: order sale — daybook head builder (zero-sum) + post orchestration."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine, zero_sum
from python_gui.modules.order_sale.service import OrderSalePostingService

sqlite3.register_adapter(Decimal, str)

_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode", "vtype"}
_DP = {"slno", "vchno", "particular", "tdate"}
_SM = {"slno", "billno", "tdate", "custcode", "custname", "billamt", "netamt", "discount",
       "eamt", "sretamt", "orderno", "control", "status", "sr"}
_SD = {"slno", "sno", "code", "qty", "weight", "stonewgt", "amount", "mcharge", "rate", "stktype"}
_OM = {"slno", "ordno", "status", "salebill"}
_ITEMS = {"code", "qty", "weight", "stonewgt", "qtyb", "weightb", "stonewgtb"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT, vtype TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, tdate TEXT)"))
        c.execute(text("CREATE TABLE salesm (slno INT, billno TEXT, tdate TEXT, custcode TEXT, custname TEXT, billamt NUM, netamt NUM, discount NUM, eamt NUM, sretamt NUM, orderno TEXT, control INT, status INT, sr TEXT)"))
        c.execute(text("CREATE TABLE salesd (slno INT, sno INT, code TEXT, qty INT, weight NUM, stonewgt NUM, amount NUM, mcharge NUM, rate NUM, stktype TEXT)"))
        c.execute(text("CREATE TABLE orderm (slno INT, ordno TEXT, status INT, salebill TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE generals (code TEXT PRIMARY KEY, cvalue TEXT)"))
        c.execute(text("CREATE TABLE items (code TEXT, qty INT, weight NUM, stonewgt NUM, qtyb INT, weightb NUM, stonewgtb NUM)"))
        c.execute(text("CREATE TABLE delpart (slno INT)"))
        c.execute(text("INSERT INTO generals VALUES ('SBPREF','GLD/')"))
        c.execute(text("INSERT INTO orderm VALUES (7,'ORD/00007',1,'')"))
        c.execute(text("INSERT INTO items VALUES ('R1',10,100.0,0,10,100.0,0)"))
    pe = PostingEngine(db)
    cmap = {"daybook": _DB, "daybookpart": _DP, "salesm": _SM, "salesd": _SD, "orderm": _OM,
            "items": _ITEMS, "generali": {"code", "cvalue"}, "generals": {"code", "cvalue"}, "delpart": {"slno"}}
    tabs = set(cmap)
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: c in cmap.get(t, set())
    pe.db.columns = lambda t: cmap.get(t, set())
    return db, pe


def _rows(db, slno):
    return db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno=:s ORDER BY rowid", {"s": slno})


def test_cash_sale_entries_zero_sum():
    _, pe = make_engine()
    svc = OrderSalePostingService(pe)
    entries = svc.build_entries({"customer_code": "", "cashbank_code": "CASH",
                                 "bill_total": 10000, "net_total": 10000, "received": 10000})
    assert zero_sum(entries) == Decimal("0.00")
    by = {e["accode"]: e for e in entries}
    assert by["CASH"]["amount"] == Decimal("-10000.00")
    assert by["RS"]["amount"] == Decimal("10000.00") and by["RS"]["opaccode"] == "CASH"


def test_credit_sale_customer_and_rs():
    _, pe = make_engine()
    entries = OrderSalePostingService(pe).build_entries(
        {"customer_code": "C1", "bill_total": 10000, "net_total": 10000, "received": 0})
    by = {e["accode"]: e for e in entries}
    assert by["C1"]["amount"] == Decimal("-10000.00")
    assert by["RS"]["amount"] == Decimal("10000.00") and by["RS"]["opaccode"] == "C1"
    assert zero_sum(entries) == Decimal("0.00")


def test_gst_split_and_exchange():
    _, pe = make_engine()
    entries = OrderSalePostingService(pe).build_entries(
        {"customer_code": "C1", "bill_total": 10000, "net_total": 10300, "tax": 300,
         "exchange_amount": 2000, "received": 0})
    by = {e["accode"]: e["amount"] for e in entries}
    assert by["SGST"] == Decimal("150.00") and by["CGST"] == Decimal("150.00")
    assert by["EP"] == Decimal("-2000.00")


def test_post_persists_and_marks_order_and_stock():
    db, pe = make_engine()
    svc = OrderSalePostingService(pe, control=1)
    res = svc.post(
        amounts={"customer_code": "C1", "customer_name": "ACME", "cashbank_code": "CASH",
                 "bill_total": 60000, "net_total": 60000, "received": 60000},
        items=[{"item_code": "R1", "qty": 1, "weight": 8.0, "amount": 60000, "stktype": ""}],
        billdate="2026-06-17", order_no="ORD/00007")
    assert res["bill_no"].startswith("GLD/")
    # daybook balanced
    assert sum(Decimal(str(r["amount"])) for r in _rows(db, res["slno"])) == Decimal("0.00")
    # salesm + salesd persisted
    assert int(db.scalar("SELECT COUNT(*) FROM salesm WHERE slno=:s", {"s": res["slno"]})) == 1
    assert int(db.scalar("SELECT COUNT(*) FROM salesd WHERE slno=:s", {"s": res["slno"]})) == 1
    # item stock decreased by 8
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='R1'"))) == Decimal("92.000")
    # order marked billed
    assert int(db.scalar("SELECT status FROM orderm WHERE ordno='ORD/00007'")) == 2
    assert db.scalar("SELECT salebill FROM orderm WHERE ordno='ORD/00007'") == res["bill_no"]
