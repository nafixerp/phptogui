"""Pending: remake issue memo (smithm/smithd memo CRUD)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.remake_issue_memo.service import RemakeIssueMemoError, RemakeIssueMemoService

sqlite3.register_adapter(Decimal, str)

_SM = {"slno", "docno", "tdate", "duedate", "smithcode", "smcode", "status", "control", "ic", "doctype"}
_SD = {"slno", "sno", "code", "name", "qty", "weight", "stonewgt", "netwgt", "givrec", "cost", "stktype", "remark"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE smithm (slno INT, docno TEXT, tdate TEXT, duedate TEXT, smithcode TEXT, smcode TEXT, status INT, control INT, ic INT, doctype TEXT)"))
        c.execute(text("CREATE TABLE smithd (slno INT, sno INT, code TEXT, name TEXT, qty INT, weight NUM, stonewgt NUM, netwgt NUM, givrec TEXT, cost NUM, stktype TEXT, remark TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    cmap = {"smithm": _SM, "smithd": _SD, "generali": {"code", "cvalue"}}
    tabs = set(cmap)
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: c in cmap.get(t, set())
    pe.db.columns = lambda t: cmap.get(t, set())
    return db, pe


def test_save_memo_header_and_items():
    db, pe = make_engine()
    res = RemakeIssueMemoService(pe).save(custcode="s1", sman="sm1",
                                          rows=[{"itemcode": "r1", "qty": 1, "weight": 12.0, "stonewgt": 2.0}])
    assert res["bill_no"].startswith("RM2/") and res["items"] == 1
    m = db.fetchone("SELECT doctype, smithcode FROM smithm WHERE slno=:s", {"s": res["slno"]})
    assert m["doctype"] == "Remake Issue" and m["smithcode"] == "S1"
    d = db.fetchone("SELECT givrec, netwgt FROM smithd WHERE slno=:s", {"s": res["slno"]})
    assert d["givrec"] == "G" and Decimal(str(d["netwgt"])) == Decimal("10.000")  # 12 - 2


def test_edit_replaces_then_cancel_deletes():
    db, pe = make_engine()
    svc = RemakeIssueMemoService(pe)
    r = svc.save(custcode="S1", rows=[{"itemcode": "R1", "weight": 5}])
    svc.save(custcode="S1", rows=[{"itemcode": "R2", "weight": 8}], mode="edit",
             slno=r["slno"], bill_no=r["bill_no"])
    assert db.scalar("SELECT code FROM smithd WHERE slno=:s", {"s": r["slno"]}) == "R2"
    svc.cancel(r["bill_no"])
    assert int(db.scalar("SELECT COUNT(*) FROM smithm WHERE slno=:s", {"s": r["slno"]})) == 0


def test_validations():
    db, pe = make_engine()
    svc = RemakeIssueMemoService(pe)
    with pytest.raises(RemakeIssueMemoError):
        svc.save(custcode="S1", rows=[{"itemcode": "R1", "weight": 0}])
    with pytest.raises(RemakeIssueMemoError):
        svc.save(custcode="S1", rows=[])
