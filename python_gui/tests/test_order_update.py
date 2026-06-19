"""Bucket B: order update (orderm/orderd manual entry)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.order_update.service import OrderUpdateError, OrderUpdateService

sqlite3.register_adapter(Decimal, str)

_OM = {"slno", "ordno", "tdate", "duedate", "custcode", "custname", "rate", "billamt", "eamt",
       "advance", "status", "control", "smcode", "gadvance", "sretamt", "ob", "addr", "refund",
       "closed", "jewlcode", "duedate_org", "ic"}
_OD = {"slno", "code", "qty", "weight", "stonewgt", "stoneprice", "mcharge", "wastage", "rate",
       "amount", "part", "sno", "iqtype", "smith"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE orderm (slno INT, ordno TEXT, tdate TEXT, duedate TEXT, custcode TEXT, custname TEXT, "
                       "rate NUM, billamt NUM, eamt NUM, advance NUM, status INT, control INT, smcode TEXT, gadvance NUM, "
                       "sretamt NUM, ob NUM, addr TEXT, refund NUM, closed INT, jewlcode TEXT, duedate_org TEXT, ic TEXT)"))
        c.execute(text("CREATE TABLE orderd (slno INT, code TEXT, qty INT, weight NUM, stonewgt NUM, stoneprice NUM, "
                       "mcharge NUM, wastage NUM, rate NUM, amount NUM, part TEXT, sno INT, iqtype TEXT, smith TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE generals (code TEXT PRIMARY KEY, cvalue TEXT)"))
        c.execute(text("INSERT INTO generals VALUES ('ORDPREF','JOB')"))
    pe = PostingEngine(db)
    tabs = {"orderm", "orderd", "generali", "generals"}
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: (c in _OM) if t == "orderm" else (c in _OD) if t == "orderd" else True
    pe.db.columns = lambda t: _OM if t == "orderm" else _OD if t == "orderd" else {"code", "cvalue"}
    return db, pe


def test_save_order_header_and_items():
    db, pe = make_engine()
    res = OrderUpdateService(pe).save(
        {"jewlcode": "G22", "custname": "ACME", "custcode": "C1", "rate": 6000, "smcode": "SM1"},
        [{"code": "r1", "qty": 1, "weight": 10, "mcharge": 500, "amount": 60500},
         {"code": "r2", "qty": 1, "weight": 5, "amount": 30000},
         {"code": "", "amount": 99}])  # invalid skipped
    assert res["ordno"].startswith("JOB/") and res["items"] == 2
    # billamt = sum of item amounts
    assert Decimal(str(db.scalar("SELECT billamt FROM orderm WHERE slno=:s", {"s": res["slno"]}))) == Decimal("90500.00")
    assert int(db.scalar("SELECT COUNT(*) FROM orderd WHERE slno=:s", {"s": res["slno"]})) == 2
    # status defaults to pending (1), advance 0
    assert int(db.scalar("SELECT status FROM orderm WHERE slno=:s", {"s": res["slno"]})) == 1
    assert db.fetchone("SELECT code FROM orderd WHERE slno=:s ORDER BY sno", {"s": res["slno"]})["code"] == "R1"


def test_order_number_increments():
    db, pe = make_engine()
    svc = OrderUpdateService(pe)
    r1 = svc.save({"jewlcode": "G", "custname": "A"}, [{"code": "x", "amount": 1}])
    r2 = svc.save({"jewlcode": "G", "custname": "B"}, [{"code": "y", "amount": 1}])
    assert r1["ordno"] != r2["ordno"] and r2["slno"] > r1["slno"]


def test_delete_removes_header_and_items():
    db, pe = make_engine()
    svc = OrderUpdateService(pe)
    res = svc.save({"jewlcode": "G", "custname": "A"}, [{"code": "x", "amount": 1}])
    svc.delete(res["slno"])
    assert int(db.scalar("SELECT COUNT(*) FROM orderm WHERE slno=:s", {"s": res["slno"]})) == 0
    assert int(db.scalar("SELECT COUNT(*) FROM orderd WHERE slno=:s", {"s": res["slno"]})) == 0


def test_save_requires_jewlcode_and_items():
    db, pe = make_engine()
    with pytest.raises(OrderUpdateError):
        OrderUpdateService(pe).save({"jewlcode": "", "custname": "A"}, [{"code": "x"}])
    with pytest.raises(OrderUpdateError):
        OrderUpdateService(pe).save({"jewlcode": "G", "custname": "A"}, [{"code": ""}])
