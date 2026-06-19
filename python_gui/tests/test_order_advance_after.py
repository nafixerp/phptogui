"""Pending: order advance-after (advafter + orderdga stock + zero-sum daybook)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.order_advance_after.service import (
    OrderAdvanceAfterError,
    OrderAdvanceAfterService,
)

sqlite3.register_adapter(Decimal, str)

_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP = {"slno", "vchno", "particular", "ic", "ttime"}
_AA = {"slno", "tdate", "docno", "amount", "ordno", "control", "ttype", "rate", "wgt", "amttowgt"}
_GA = {"slno", "sno", "code", "qty", "weight", "cost", "stktype", "stonewgt", "lessperc", "lesswgt", "iqtype", "stktouch", "tdate", "control"}
_OM = {"slno", "ordno", "custcode", "status"}
_ITEMS = {"code", "qty", "weight", "stonewgt", "qtyb", "weightb", "stonewgtb"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, ic TEXT, ttime TEXT)"))
        c.execute(text("CREATE TABLE advafter (slno INT, tdate TEXT, docno TEXT, amount NUM, ordno TEXT, control INT, ttype TEXT, rate NUM, wgt NUM, amttowgt TEXT)"))
        c.execute(text("CREATE TABLE orderdga (slno INT, sno INT, code TEXT, qty INT, weight NUM, cost NUM, stktype TEXT, stonewgt NUM, lessperc NUM, lesswgt NUM, iqtype TEXT, stktouch NUM, tdate TEXT, control INT)"))
        c.execute(text("CREATE TABLE orderm (slno INT, ordno TEXT, custcode TEXT, status INT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, qty INT, weight NUM, stonewgt NUM, qtyb INT, weightb NUM, stonewgtb NUM)"))
        c.execute(text("INSERT INTO orderm VALUES (5,'OR1','C1',1)"))
        c.execute(text("INSERT INTO items VALUES ('R1',10,100.0,0,10,100.0,0)"))
    pe = PostingEngine(db)
    cmap = {"daybook": _DB, "daybookpart": _DP, "advafter": _AA, "orderdga": _GA, "orderm": _OM,
            "items": _ITEMS, "generali": {"code", "cvalue"}}
    tabs = set(cmap)
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: c in cmap.get(t, set())
    pe.db.columns = lambda t: cmap.get(t, set())
    return db, pe


def _rows(db, slno):
    return db.fetchall("SELECT accode, amount FROM daybook WHERE slno=:s ORDER BY rowid", {"s": slno})


def test_cash_advance_zero_sum_and_advafter():
    db, pe = make_engine()
    res = OrderAdvanceAfterService(pe).save(ordno="or1", tdate="2026-06-17", amount=5000, cashbank_code="CASH")
    assert res["balanced"] and res["vchno"].startswith("VRB/")
    rows = {r["accode"]: r["amount"] for r in _rows(db, res["slno"])}
    # customer debit + ; cash credit -
    assert rows["C1"] == Decimal("5000.00") and rows["CASH"] == Decimal("-5000.00")
    # advafter row written
    aa = db.fetchone("SELECT amount, ordno FROM advafter WHERE slno=:s", {"s": res["slno"]})
    assert Decimal(str(aa["amount"])) == Decimal("5000.00") and aa["ordno"] == "OR1"


def test_advance_with_metal_increases_stock():
    db, pe = make_engine()
    res = OrderAdvanceAfterService(pe).save(
        ordno="OR1", tdate="2026-06-17", amount=0,
        items=[{"code": "r1", "qty": 1, "weight": 8.0, "stonewgt": 0}])
    # item stock increased by metal advance
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='R1'"))) == Decimal("108.000")
    assert int(db.scalar("SELECT COUNT(*) FROM orderdga WHERE slno=:s", {"s": res["slno"]})) == 1
    # dtwgt = 8 - 0 - 0
    assert res["dtwgt"] == Decimal("8.000")


def test_invalid_order_rejected():
    db, pe = make_engine()
    with pytest.raises(OrderAdvanceAfterError):
        OrderAdvanceAfterService(pe).save(ordno="ZZZ", tdate="2026-06-17", amount=100)
    with pytest.raises(OrderAdvanceAfterError):
        OrderAdvanceAfterService(pe).save(ordno="", tdate="2026-06-17", amount=100)
