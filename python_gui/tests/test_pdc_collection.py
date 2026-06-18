"""Bucket B: PDC collection / clearance — daybook posting + pdclist update."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.pdc_collection.service import PdcCollectionService

sqlite3.register_adapter(Decimal, str)

_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP = {"slno", "vchno", "particular", "chequeno", "chequedate", "uid", "tdate", "ttime"}
_PDC = {"slno", "docno", "tdate", "bank", "code", "chqno", "chqdate", "amount", "particulars",
        "rp", "pend", "control", "colndate", "bankexp", "scharge", "slno2", "bounced"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, chequeno TEXT, chequedate TEXT, uid TEXT, tdate TEXT, ttime TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE pdclist (slno INT, docno TEXT, tdate TEXT, bank TEXT, code TEXT, chqno TEXT, "
                       "chqdate TEXT, amount NUM, particulars TEXT, rp TEXT, pend TEXT, control INT, colndate TEXT, "
                       "bankexp NUM, scharge NUM, slno2 INT, bounced TEXT)"))
        # a pending receipt cheque for party C1 via HDFC
        c.execute(text("INSERT INTO pdclist VALUES (5,'PD1','2026-06-01','HDFC','C1','CHQ1','2026-06-20',10000,'Sale adv','R','Y',1,NULL,0,0,0,'N')"))
    pe = PostingEngine(db)
    tabs = {"daybook", "daybookpart", "generali", "pdclist"}
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: (c in _DB) if t == "daybook" else (c in _DP) if t == "daybookpart" else (c in _PDC) if t == "pdclist" else True
    pe.db.columns = lambda t: _DB if t == "daybook" else _DP if t == "daybookpart" else _PDC if t == "pdclist" else set()
    return db, pe


def _rows(db, slno):
    return db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno = :s ORDER BY rowid", {"s": slno})


def test_receipt_clearance_zero_sum_no_expense():
    db, pe = make_engine()
    res = PdcCollectionService(pe).collect(
        chequeno="CHQ1", tdate="2026-06-20", party_code="C1", bank="HDFC",
        amount=10000, net_amount=10000, sidocno="PD1")
    assert res["balanced"] is True and res["lines"] == 2
    rows = {r["accode"]: r for r in _rows(db, res["slno"])}
    assert rows["C1"]["amount"] == Decimal("10000.00") and rows["C1"]["opaccode"] == "HDFC"
    assert rows["HDFC"]["amount"] == Decimal("-10000.00")
    # voucher series R + control1 -> VRB/
    assert res["vchno"].startswith("VRB/")
    # pdclist marked collected
    assert db.scalar("SELECT pend FROM pdclist WHERE docno='PD1'") == "N"
    assert int(db.scalar("SELECT slno2 FROM pdclist WHERE docno='PD1'")) == res["slno"]


def test_receipt_clearance_with_bank_expense_zero_sum():
    db, pe = make_engine()
    # amount 10000, bank expense 200 -> net = 9800
    res = PdcCollectionService(pe).collect(
        chequeno="CHQ1", tdate="2026-06-20", party_code="C1", bank="HDFC",
        amount=10000, net_amount=9800, expense=200, sidocno="PD1")
    assert res["balanced"] is True
    rows = {r["accode"]: r for r in _rows(db, res["slno"])}
    assert rows["C1"]["amount"] == Decimal("10000.00")
    assert rows["HDFC"]["amount"] == Decimal("-9800.00")
    assert rows["BEXP"]["amount"] == Decimal("-200.00")


def test_serial_advances_across_calls():
    db, pe = make_engine()
    svc = PdcCollectionService(pe)
    r1 = svc.collect(chequeno="CHQ1", tdate="2026-06-20", party_code="C1", bank="HDFC",
                     amount=10000, net_amount=10000, sidocno="PD1")
    r2 = svc.collect(chequeno="CHQ1", tdate="2026-06-21", party_code="C1", bank="HDFC",
                     amount=5000, net_amount=5000, sidocno="")
    assert r2["slno"] > r1["slno"]
    # voucher counter advanced
    assert r1["vchno"] != r2["vchno"]
