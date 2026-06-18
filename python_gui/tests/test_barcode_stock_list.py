"""Barcode stock list (filters + totals) and verification lookup."""

from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.barcode_stock.service import BarcodeStockService


def make():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE barcode (bcode INT, icode TEXT, qty NUM, weight NUM, qtype TEXT, counter TEXT, stk TEXT)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("INSERT INTO items VALUES ('GOLD22','22K Gold')"))
        c.execute(text("INSERT INTO barcode VALUES (100001,'GOLD22',1,10,'22K','C1','Y')"))
        c.execute(text("INSERT INTO barcode VALUES (100002,'GOLD22',1,20,'22K','C1','Y')"))
        c.execute(text("INSERT INTO barcode VALUES (100003,'GOLD22',1,5,'22K','C2','N')"))
    db.table_exists = lambda t: t in ("barcode", "items")
    return db, BarcodeStockService(db)


def test_stock_list_in_stock_only_and_totals():
    db, svc = make()
    res = svc.list_stock()
    assert len(res["rows"]) == 2
    assert res["total_weight"] == Decimal("30.000")


def test_stock_list_counter_filter():
    db, svc = make()
    res = svc.list_stock(counter="C1")
    assert {r["bcode"] for r in res["rows"]} == {100001, 100002}


def test_verification_in_stock():
    db, svc = make()
    info = svc.lookup(100001)
    assert info["in_stock"] is True and info["out_of_stock"] is False
    assert info["itemname"] == "22K Gold"


def test_verification_sold():
    db, svc = make()
    info = svc.lookup(100003)
    assert info["out_of_stock"] is True and info["in_stock"] is False


def test_verification_not_found():
    db, svc = make()
    assert svc.lookup(999999) is None
