"""Bucket B: party bill-wise receipt/payment — zero-sum daybook + collection."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.party_billwise.service import PartyBillwiseError, PartyBillwiseService

sqlite3.register_adapter(Decimal, str)

_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP = {"slno", "vchno", "particular", "staff", "tdate", "ic", "uid", "control"}
_COL = {"slno", "code", "tdate", "billno", "tranamt", "discount", "duedate", "control", "islno", "grate", "grate2", "cbcode"}
_SM = {"slno", "ramtafter", "duedate"}
_PM = {"slno", "pamtafter", "duedate"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, staff TEXT, tdate TEXT, ic TEXT, uid TEXT, control INT)"))
        c.execute(text("CREATE TABLE collection (slno INT, code TEXT, tdate TEXT, billno TEXT, tranamt NUM, discount NUM, duedate TEXT, control INT, islno INT, grate NUM, grate2 NUM, cbcode TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE salesm (slno INT, ramtafter NUM, duedate TEXT)"))
        c.execute(text("CREATE TABLE purchasem (slno INT, pamtafter NUM, duedate TEXT)"))
        c.execute(text("INSERT INTO salesm VALUES (101,0,NULL)"))
        c.execute(text("INSERT INTO purchasem VALUES (201,0,NULL)"))
    pe = PostingEngine(db)
    cmap = {"daybook": _DB, "daybookpart": _DP, "collection": _COL, "salesm": _SM,
            "purchasem": _PM, "generali": {"code", "cvalue"}}
    tabs = set(cmap)
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: c in cmap.get(t, set())
    pe.db.columns = lambda t: cmap.get(t, set())
    return db, pe


def _rows(db, slno):
    return db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno=:s ORDER BY rowid", {"s": slno})


def test_customer_receipt_zero_sum_and_collection():
    db, pe = make_engine()
    svc = PartyBillwiseService(pe, "receipt", control=1)
    res = svc.post(partycode="c1", tdate="2026-06-17",
                   items=[{"slno": 101, "billno": "S1", "balance": 5000, "alocamt": 5000, "discamt": 0, "selected": True}])
    assert res["saved"] and res["vchno"].startswith("VRB/")
    rows = {r["accode"]: r for r in _rows(db, res["slno"])}
    assert rows["C1"]["amount"] == Decimal("5000.00")   # customer debit +
    assert rows["CASH"]["amount"] == Decimal("-5000.00")
    # collection + salesm.ramtafter updated
    assert Decimal(str(db.scalar("SELECT tranamt FROM collection WHERE slno=:s", {"s": res["slno"]}))) == Decimal("5000.00")
    assert Decimal(str(db.scalar("SELECT ramtafter FROM salesm WHERE slno=101"))) == Decimal("5000.00")


def test_supplier_payment_signs_flipped():
    db, pe = make_engine()
    svc = PartyBillwiseService(pe, "payment", control=1)
    res = svc.post(partycode="S1", tdate="2026-06-17", cbcode="HDFC",
                   items=[{"slno": 201, "billno": "P1", "balance": 8000, "alocamt": 8000, "discamt": 0, "selected": True}])
    assert res["vchno"].startswith("VPB/")
    rows = {r["accode"]: r for r in _rows(db, res["slno"])}
    assert rows["S1"]["amount"] == Decimal("-8000.00")  # supplier credit -
    assert rows["HDFC"]["amount"] == Decimal("8000.00")
    assert Decimal(str(db.scalar("SELECT pamtafter FROM purchasem WHERE slno=201"))) == Decimal("8000.00")


def test_receipt_with_discount_posts_second_voucher():
    db, pe = make_engine()
    svc = PartyBillwiseService(pe, "receipt", control=1)
    res = svc.post(partycode="C1", tdate="2026-06-17",
                   items=[{"slno": 101, "billno": "S1", "balance": 5000, "alocamt": 4500, "discamt": 500, "selected": True}])
    # main receipt voucher balanced
    assert sum(Decimal(str(r["amount"])) for r in _rows(db, res["slno"])) == Decimal("0.00")
    # a second (discount) voucher exists on a different slno, also balanced
    disc_slno = int(db.scalar("SELECT MAX(slno) FROM daybook"))
    assert disc_slno != res["slno"]
    drows = {r["accode"]: r for r in _rows(db, disc_slno)}
    assert drows["C1"]["amount"] == Decimal("500.00") and drows["DISC"]["amount"] == Decimal("-500.00")


def test_over_allocation_rejected():
    db, pe = make_engine()
    svc = PartyBillwiseService(pe, "receipt")
    with pytest.raises(PartyBillwiseError):
        svc.post(partycode="C1", tdate="2026-06-17",
                 items=[{"slno": 101, "billno": "S1", "balance": 1000, "alocamt": 5000, "selected": True}])
