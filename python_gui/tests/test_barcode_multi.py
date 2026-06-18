"""Bucket B: barcode multi-entry (bulk barcode upsert)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.barcode_multi.service import BarcodeMultiError, BarcodeMultiService

sqlite3.register_adapter(Decimal, str)

_BC = {"bcode", "icode", "qty", "weight", "stweight", "stprice", "wastage", "mc", "tdate",
       "smcode", "control", "mcrate", "rslno", "islno", "stk", "rate", "smithmcrate",
       "weight2", "vap", "sizemodel", "model", "counter", "subgrp", "minvap", "stkinnos",
       "docno", "status", "smithcode", "huid"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE barcode (bcode INT PRIMARY KEY, icode TEXT, qty INT, weight NUM, stweight NUM, "
                       "stprice NUM, wastage NUM, mc NUM, tdate TEXT, smcode TEXT, control INT, mcrate NUM, rslno INT, "
                       "islno INT, stk TEXT, rate NUM, smithmcrate NUM, weight2 NUM, vap NUM, sizemodel TEXT, model TEXT, "
                       "counter TEXT, subgrp TEXT, minvap NUM, stkinnos TEXT, docno TEXT, status TEXT, smithcode TEXT, huid TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    tabs = {"barcode", "generali"}
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: (c in _BC) if t == "barcode" else True
    pe.db.columns = lambda t: _BC if t == "barcode" else {"code", "cvalue"}
    return db, pe


def test_save_inserts_rows_and_advances_bcno():
    db, pe = make_engine()
    res = BarcodeMultiService(pe, control=1).save([
        {"barcode": 1000001, "itemcode": "r1", "qty": 1, "weight": 10.5, "stwgt": 1.5, "mcrate": 300},
        {"barcode": 1000002, "itemcode": "r2", "qty": 1, "weight": 5.0},
        {"barcode": 0, "itemcode": "bad", "weight": 1},  # invalid -> skipped
    ], tdate="2026-06-17")
    assert res["saved"] == 2
    assert res["docno"].startswith("BC/")
    r = db.fetchone("SELECT * FROM barcode WHERE bcode=1000001")
    assert r["icode"] == "R1" and r["stk"] == "Y"
    assert Decimal(str(r["weight2"])) == Decimal("10.500")  # weight + 0 sticker
    # BCNO advanced to the highest bcode
    assert int(db.scalar("SELECT cvalue FROM generali WHERE code='BCNO'")) == 1000002


def test_next_barcode_uses_max():
    db, pe = make_engine()
    svc = BarcodeMultiService(pe)
    assert svc.next_barcode() == 1_000_001  # empty -> floor + 1
    svc.save([{"barcode": 2000000, "itemcode": "r1", "weight": 3}])
    assert svc.next_barcode() == 2000001


def test_save_upserts_existing_barcode():
    db, pe = make_engine()
    svc = BarcodeMultiService(pe)
    svc.save([{"barcode": 5000, "itemcode": "r1", "weight": 3}])
    svc.save([{"barcode": 5000, "itemcode": "r1", "weight": 9}])
    assert int(db.scalar("SELECT COUNT(*) FROM barcode WHERE bcode=5000")) == 1
    assert Decimal(str(db.scalar("SELECT weight FROM barcode WHERE bcode=5000"))) == Decimal("9.000")


def test_save_rejects_empty():
    db, pe = make_engine()
    with pytest.raises(BarcodeMultiError):
        BarcodeMultiService(pe).save([])
