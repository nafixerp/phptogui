"""Bucket B: refinery bill issue — refinerym/refineryd + stock decrease."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.refinery_bill.service import RefineryBillError, RefineryBillService

sqlite3.register_adapter(Decimal, str)

_RM = {"slno", "docno", "tdate", "ttime", "refcode", "tbottlestk", "ttestpcs", "charge", "paidamt",
       "toldissuedwgt", "testperc", "status", "control", "smcode", "ic", "expwgt", "note"}
_RD = {"slno", "code", "issuedwgt", "issuedqty", "rcvdwgt", "rcvdqty", "bottlestk", "testpcs",
       "oissuedwgt", "status", "cost", "rate", "rcvdwgtamt", "issuedwgtamt", "sno", "mudless",
       "coper", "stktype", "issuedstwgt", "stktouch", "touch"}
_ITEMS = {"code", "qty", "weight", "stonewgt", "qtyb", "weightb", "stonewgtb"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE refinerym (slno INT, docno TEXT, tdate TEXT, ttime TEXT, refcode TEXT, tbottlestk NUM, "
                       "ttestpcs NUM, charge NUM, paidamt NUM, toldissuedwgt NUM, testperc NUM, status INT, control INT, "
                       "smcode TEXT, ic TEXT, expwgt NUM, note TEXT)"))
        c.execute(text("CREATE TABLE refineryd (slno INT, code TEXT, issuedwgt NUM, issuedqty INT, rcvdwgt NUM, rcvdqty INT, "
                       "bottlestk NUM, testpcs NUM, oissuedwgt NUM, status INT, cost NUM, rate NUM, rcvdwgtamt NUM, "
                       "issuedwgtamt NUM, sno INT, mudless NUM, coper NUM, stktype TEXT, issuedstwgt NUM, stktouch NUM, touch NUM)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, qty INT, weight NUM, stonewgt NUM, qtyb INT, weightb NUM, stonewgtb NUM)"))
        c.execute(text("INSERT INTO items VALUES ('OG',5,100.0,0,5,100.0,0)"))
        c.execute(text("INSERT INTO items VALUES ('TP',0,0,0,0,0,0)"))
    pe = PostingEngine(db)
    tabs = {"refinerym", "refineryd", "generali", "items"}
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: (c in _RM) if t == "refinerym" else (c in _RD) if t == "refineryd" else (c in _ITEMS) if t == "items" else True
    pe.db.columns = lambda t: _RM if t == "refinerym" else _RD if t == "refineryd" else _ITEMS if t == "items" else {"code", "cvalue"}
    return db, pe


def test_issue_writes_header_detail_and_decreases_stock():
    db, pe = make_engine()
    res = RefineryBillService(pe).save(refiner_code="r1", items=[
        {"item_code": "OG", "qty": 2, "weight": 40.0, "stone_wgt": 0, "test_pcs": 1.5, "touch": 91.6, "stktype": ""}])
    assert res["doc_no"].startswith("RFB/") and res["items"] == 1
    # header + detail persisted
    assert int(db.scalar("SELECT COUNT(*) FROM refineryd WHERE slno=:s", {"s": res["slno"]})) == 1
    assert Decimal(str(db.scalar("SELECT toldissuedwgt FROM refinerym WHERE slno=:s", {"s": res["slno"]}))) == Decimal("40.000")
    # OG decreased by 40 (control 1 hits both weight and weightb)
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='OG'"))) == Decimal("60.000")
    assert int(db.scalar("SELECT qty FROM items WHERE code='OG'")) == 3
    # TP credited test pieces 1.5
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='TP'"))) == Decimal("1.500")


def test_edit_reverses_then_reapplies():
    db, pe = make_engine()
    svc = RefineryBillService(pe)
    r1 = svc.save(refiner_code="R1", items=[{"item_code": "OG", "qty": 1, "weight": 30.0, "test_pcs": 0}])
    # OG now 70
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='OG'"))) == Decimal("70.000")
    # re-save same doc with a smaller weight -> reverse 30 then issue 10 => OG = 100 - 10 = 90
    svc.save(refiner_code="R1", items=[{"item_code": "OG", "qty": 1, "weight": 10.0, "test_pcs": 0}], doc_no=r1["doc_no"])
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='OG'"))) == Decimal("90.000")


def test_rejects_zero_weight_and_empty():
    db, pe = make_engine()
    with pytest.raises(RefineryBillError):
        RefineryBillService(pe).save(refiner_code="R1", items=[{"item_code": "OG", "weight": 0}])
    with pytest.raises(RefineryBillError):
        RefineryBillService(pe).save(refiner_code="", items=[{"item_code": "OG", "weight": 5}])
