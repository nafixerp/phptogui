"""Bucket B: repair return — repairm/repaird + stock decrease + zero-sum daybook."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.repair_return.service import RepairReturnError, RepairReturnService

sqlite3.register_adapter(Decimal, str)

_RM = {"slno", "billno", "tdate", "duedate", "custcode", "custname", "amount", "discount", "rcvd",
       "givrec", "status", "rbillno", "control", "addr", "sman", "ic", "smith", "advance", "taxperc", "taxamt"}
_RD = {"slno", "code", "name", "weight", "qty", "stonewgt", "stoneprice", "wastage", "mcharge", "addwgt",
       "amount", "givrec", "complaint", "rate", "cost", "sno", "netwgt", "purity", "mark", "stktype"}
_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode", "ttype"}
_DP = {"slno", "vchno", "particular", "ic", "uid", "ttime", "taxamt", "tdate"}
_ITEMS = {"code", "qty", "weight", "stonewgt", "qtyb", "weightb", "stonewgtb"}
_CLIENTS = {"code", "name", "balance"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE repairm (slno INT, billno TEXT, tdate TEXT, custcode TEXT, custname TEXT, amount NUM, "
                       "discount NUM, rcvd NUM, givrec TEXT, status INT, rbillno TEXT, control INT, sman TEXT, ic INT, taxperc NUM, taxamt NUM)"))
        c.execute(text("CREATE TABLE repaird (slno INT, code TEXT, name TEXT, weight NUM, qty INT, stonewgt NUM, wastage NUM, "
                       "mcharge NUM, addwgt NUM, amount NUM, givrec TEXT, rate NUM, cost NUM, sno INT, netwgt NUM, stktype TEXT)"))
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT, ttype TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, ic TEXT, uid TEXT, ttime TEXT, taxamt NUM, tdate TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, qty INT, weight NUM, stonewgt NUM, qtyb INT, weightb NUM, stonewgtb NUM)"))
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, balance NUM)"))
        c.execute(text("INSERT INTO items VALUES ('R1',10,100.0,0,10,100.0,0)"))
        c.execute(text("INSERT INTO clients VALUES ('C1','ACME',0)"))
        c.execute(text("CREATE TABLE delpart (slno INT)"))
    pe = PostingEngine(db)
    cmap = {"repairm": _RM, "repaird": _RD, "daybook": _DB, "daybookpart": _DP,
            "items": _ITEMS, "clients": _CLIENTS, "generali": {"code", "cvalue"}, "delpart": {"slno"}}
    tabs = set(cmap)
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: c in cmap.get(t, set())
    pe.db.columns = lambda t: cmap.get(t, set())
    return db, pe


def _rows(db, slno):
    return db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno=:s ORDER BY rowid", {"s": slno})


def test_repair_return_posts_zero_sum_and_decreases_stock():
    db, pe = make_engine()
    res = RepairReturnService(pe, control=1).save(
        {"custcode": "c1", "custname": "ACME", "sman": "sm1", "amount": 5000, "taxamt": 150,
         "discount": 0, "rcvd": 2000, "cashbank_code": "CASH"},
        [{"itemcode": "r1", "qty": 1, "weight": 8.0, "stonewgt": 0, "netwgt": 8.0, "amount": 5000, "stktype": ""}])
    assert res["balanced"] is True
    assert res["bill_no"].startswith("RM4/")
    # daybook: cust -5150 (RS), CASH -2000 (cust), cust +2000 (CASH), RS +5150 (cust) -> sum 0
    rows = _rows(db, res["slno"])
    total = sum(Decimal(str(r["amount"])) for r in rows)
    assert total == Decimal("0.00")
    by_rs = [r for r in rows if r["accode"] == "RS"]
    assert any(Decimal(str(r["amount"])) == Decimal("5150.00") for r in by_rs)
    # item stock decreased by 8 (control 1 -> weight + weightb)
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='R1'"))) == Decimal("92.000")
    # client balance += net (5000+150-0-2000 = 3150)
    assert Decimal(str(db.scalar("SELECT balance FROM clients WHERE code='C1'"))) == Decimal("3150.00")


def test_repair_return_edit_reverses_then_reapplies():
    db, pe = make_engine()
    svc = RepairReturnService(pe, control=1)
    r1 = svc.save(
        {"custcode": "C1", "custname": "ACME", "sman": "SM1", "amount": 5000, "taxamt": 0, "rcvd": 0},
        [{"itemcode": "R1", "qty": 1, "weight": 8.0, "netwgt": 8.0, "amount": 5000}])
    # stock 92, balance 5000
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='R1'"))) == Decimal("92.000")
    # edit: smaller bill, weight 3 -> reverse old (stock back to 100, bal back to 0) then apply new
    svc.save(
        {"slno": r1["slno"], "bill_no": r1["bill_no"], "custcode": "C1", "custname": "ACME",
         "sman": "SM1", "amount": 3000, "taxamt": 0, "rcvd": 0},
        [{"itemcode": "R1", "qty": 1, "weight": 3.0, "netwgt": 3.0, "amount": 3000}], mode="edit")
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='R1'"))) == Decimal("97.000")
    assert Decimal(str(db.scalar("SELECT balance FROM clients WHERE code='C1'"))) == Decimal("3000.00")


def test_repair_return_validations():
    db, pe = make_engine()
    svc = RepairReturnService(pe)
    with pytest.raises(RepairReturnError):
        svc.save({"custcode": "C1", "sman": "SM1", "amount": 5000}, [{"itemcode": "R1", "weight": 0}])
    with pytest.raises(RepairReturnError):
        svc.save({"custcode": "C1", "sman": "", "amount": 5000}, [{"itemcode": "R1", "weight": 1}])
    with pytest.raises(RepairReturnError):
        svc.save({"custcode": "C1", "sman": "SM1", "amount": 0}, [{"itemcode": "R1", "weight": 1}])
