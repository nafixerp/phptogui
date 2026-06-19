"""Pending: repair receipt memo (repairm/repaird + optional zero-sum receipt)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.repair_receipt_memo.service import RepairReceiptMemoError, RepairReceiptMemoService

sqlite3.register_adapter(Decimal, str)

_RM = {"slno", "billno", "tdate", "duedate", "custcode", "custname", "givrec", "control", "status",
       "sman", "addr", "ic", "refbillno", "refbill", "pamt", "ramt", "recvamt", "cbcode", "note", "remark"}
_RD = {"slno", "code", "name", "qty", "weight", "stonewgt", "complaint", "givrec", "cost", "sno", "netwgt", "purity", "stktype"}
_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP = {"slno", "particular", "vchno", "ic", "uid", "ttime"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE repairm (slno INT, billno TEXT, tdate TEXT, duedate TEXT, custcode TEXT, custname TEXT, givrec TEXT, control INT, status INT, sman TEXT, addr TEXT, ic INT, refbillno TEXT, refbill TEXT, pamt NUM, ramt NUM, recvamt NUM, cbcode TEXT, note TEXT, remark TEXT)"))
        c.execute(text("CREATE TABLE repaird (slno INT, code TEXT, name TEXT, qty INT, weight NUM, stonewgt NUM, complaint TEXT, givrec TEXT, cost NUM, sno INT, netwgt NUM, purity TEXT, stktype TEXT)"))
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, particular TEXT, vchno TEXT, ic INT, uid INT, ttime TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    cmap = {"repairm": _RM, "repaird": _RD, "daybook": _DB, "daybookpart": _DP, "generali": {"code", "cvalue"}}
    tabs = set(cmap)
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: c in cmap.get(t, set())
    pe.db.columns = lambda t: cmap.get(t, set())
    return db, pe


def _rows(db, slno):
    return db.fetchall("SELECT accode, amount FROM daybook WHERE slno=:s ORDER BY rowid", {"s": slno})


def test_memo_with_advance_posts_zero_sum_receipt():
    db, pe = make_engine()
    res = RepairReceiptMemoService(pe).save(custcode="c1", custname="ACME",
                                            rows=[{"itemcode": "r1", "weight": 8.0, "stonewgt": 1.0, "complaint": "polish"}],
                                            recvamt=500, cbcode="CASH")
    assert res["bill_no"].startswith("RP/") and res["balanced"]
    m = db.fetchone("SELECT givrec, recvamt FROM repairm WHERE slno=:s", {"s": res["slno"]})
    assert m["givrec"] == "R" and Decimal(str(m["recvamt"])) == Decimal("500.00")
    rows = {r["accode"]: r["amount"] for r in _rows(db, res["slno"])}
    assert rows["C1"] == Decimal("500.00") and rows["CASH"] == Decimal("-500.00")
    assert db.fetchone("SELECT givrec, netwgt FROM repaird WHERE slno=:s", {"s": res["slno"]})["givrec"] == "R"


def test_memo_without_advance_no_daybook():
    db, pe = make_engine()
    res = RepairReceiptMemoService(pe).save(custcode="C1", rows=[{"itemcode": "R1", "weight": 5}], recvamt=0)
    assert int(db.scalar("SELECT COUNT(*) FROM daybook WHERE slno=:s", {"s": res["slno"]})) == 0


def test_cancel_deletes():
    db, pe = make_engine()
    svc = RepairReceiptMemoService(pe)
    r = svc.save(custcode="C1", rows=[{"itemcode": "R1", "weight": 5}], recvamt=200)
    svc.cancel(r["bill_no"])
    assert int(db.scalar("SELECT COUNT(*) FROM repairm WHERE slno=:s", {"s": r["slno"]})) == 0
    assert int(db.scalar("SELECT COUNT(*) FROM daybook WHERE slno=:s", {"s": r["slno"]})) == 0


def test_validations():
    db, pe = make_engine()
    with pytest.raises(RepairReceiptMemoError):
        RepairReceiptMemoService(pe).save(custcode="C1", rows=[{"itemcode": "R1", "weight": 0}])
