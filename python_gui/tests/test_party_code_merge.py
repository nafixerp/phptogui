"""Pending: party code merge (re-key across tables + opening-balance carry)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.party_code_merge.service import PartyCodeMergeError, PartyCodeMergeService

sqlite3.register_adapter(Decimal, str)

_COLMAP = {
    "daybook": {"slno", "accode", "opaccode", "amount"},
    "salesm": {"slno", "custcode", "billamt"},
    "purchasem": {"slno", "suppcode"},
    "pdclist": {"slno", "code"},
    "accountm": {"accode", "name", "opbal", "opbalb"},
    "clients": {"code", "name", "cocode"},
}


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, accode TEXT, opaccode TEXT, amount NUM)"))
        c.execute(text("CREATE TABLE salesm (slno INT, custcode TEXT, billamt NUM)"))
        c.execute(text("CREATE TABLE purchasem (slno INT, suppcode TEXT)"))
        c.execute(text("CREATE TABLE pdclist (slno INT, code TEXT)"))
        c.execute(text("CREATE TABLE accountm (accode TEXT, name TEXT, opbal NUM, opbalb NUM)"))
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, cocode TEXT)"))
        # target T1 + two source codes S1, S2
        c.execute(text("INSERT INTO accountm VALUES ('T1','Target',1000,500)"))
        c.execute(text("INSERT INTO accountm VALUES ('S1','Src1',300,100)"))
        c.execute(text("INSERT INTO accountm VALUES ('S2','Src2',200,0)"))
        c.execute(text("INSERT INTO clients VALUES ('T1','Target','')"))
        c.execute(text("INSERT INTO clients VALUES ('S1','Src1','')"))
        c.execute(text("INSERT INTO daybook VALUES (1,'S1','CASH',500)"))
        c.execute(text("INSERT INTO daybook VALUES (2,'CASH','S2',-200)"))
        c.execute(text("INSERT INTO salesm VALUES (1,'S1',5000)"))
        c.execute(text("INSERT INTO pdclist VALUES (1,'S2')"))
    db.table_exists = lambda t: t in _COLMAP
    db.column_exists = lambda t, c: c in _COLMAP.get(t, set())
    db.columns = lambda t: _COLMAP.get(t, set())
    return db


def test_merge_rekeys_and_carries_balances():
    db = make_db()
    res = PartyCodeMergeService(db).merge(["s1", "s2"], "t1", delete_sources=True)
    # references re-keyed: daybook.accode(1), daybook.opaccode(1), salesm(1), pdclist(1) = 4
    assert res["reference_rows_updated"] == 4
    assert db.scalar("SELECT accode FROM daybook WHERE slno=1") == "T1"
    assert db.scalar("SELECT opaccode FROM daybook WHERE slno=2") == "T1"
    assert db.scalar("SELECT custcode FROM salesm WHERE slno=1") == "T1"
    assert db.scalar("SELECT code FROM pdclist WHERE slno=1") == "T1"
    # opening balances carried: T1 opbal = 1000 + 300 + 200 = 1500 ; opbalb = 500 + 100 = 600
    assert Decimal(str(db.scalar("SELECT opbal FROM accountm WHERE accode='T1'"))) == Decimal("1500.00")
    assert Decimal(str(db.scalar("SELECT opbalb FROM accountm WHERE accode='T1'"))) == Decimal("600.00")
    assert res["opening_balances_moved"] == 2
    # source masters deleted
    assert int(db.scalar("SELECT COUNT(*) FROM accountm WHERE accode IN ('S1','S2')")) == 0
    assert int(db.scalar("SELECT COUNT(*) FROM clients WHERE code='S1'")) == 0


def test_merge_keep_sources():
    db = make_db()
    PartyCodeMergeService(db).merge(["S1"], "T1", delete_sources=False)
    # references moved but source master retained
    assert int(db.scalar("SELECT COUNT(*) FROM accountm WHERE accode='S1'")) == 1


def test_merge_validations():
    db = make_db(); svc = PartyCodeMergeService(db)
    with pytest.raises(PartyCodeMergeError):
        svc.merge(["S1"], "")
    with pytest.raises(PartyCodeMergeError):
        svc.merge([], "T1")
    with pytest.raises(PartyCodeMergeError):
        svc.merge(["T1"], "T1")  # source==target filtered -> empty
