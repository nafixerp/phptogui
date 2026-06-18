"""Kuri/Scheme collection posting (zero-sum) + Smith Book weight read."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine, zero_sum
from python_gui.modules.kuri_collection.service import KuriError, KuriCollectionService
from python_gui.modules.smith_book.service import SmithBookService

sqlite3.register_adapter(Decimal, str)
_DB_COLS = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP_COLS = {"slno", "vchno", "particular", "staff", "tdate", "control"}
_KC_COLS = {"slno", "tdate", "code", "amount", "control", "sno", "grate", "agent", "rcptno", "closed", "wgt", "docno", "note"}


def make():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, staff TEXT, tdate TEXT, control INT)"))
        c.execute(text("CREATE TABLE kuricolln (slno INT, tdate TEXT, code TEXT, amount NUM, control INT, sno INT, grate NUM, agent TEXT, rcptno TEXT, closed TEXT, wgt NUM, docno TEXT, note TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    pe.db.table_exists = lambda t: t in ("daybook", "daybookpart", "kuricolln", "generali")
    pe.db.column_exists = lambda t, c: True
    pe.db.columns = lambda t: _DB_COLS if t == "daybook" else _DP_COLS if t == "daybookpart" else _KC_COLS if t == "kuricolln" else set()
    return db, KuriCollectionService(pe)


def test_kuri_collection_balances_and_records():
    db, svc = make()
    res = svc.collect([{"code": "SCH001", "amount": "1000", "agent": "AG1", "rcptno": "5"}],
                      "2026-06-17", "CASH", "0")
    assert res["saved"] == 1
    slno = res["rows"][0]["slno"]
    rows = db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno = :s", {"s": slno})
    by = {r["accode"]: Decimal(str(r["amount"])) for r in rows}
    assert by["SCH001"] == Decimal("1000.00")
    assert by["CASH"] == Decimal("-1000.00")
    assert zero_sum(rows) == Decimal("0.00")
    kc = db.fetchone("SELECT code, amount, rcptno FROM kuricolln WHERE slno = :s", {"s": slno})
    assert kc["code"] == "SCH001" and kc["rcptno"] == "5"


def test_kuri_refund_negative_amount_balances():
    db, svc = make()
    res = svc.collect([{"code": "SCH001", "amount": "-500"}], "2026-06-17", "CASH", "0")
    slno = res["rows"][0]["slno"]
    rows = db.fetchall("SELECT accode, amount FROM daybook WHERE slno = :s", {"s": slno})
    assert zero_sum(rows) == Decimal("0.00")
    by = {r["accode"]: Decimal(str(r["amount"])) for r in rows}
    assert by["SCH001"] == Decimal("-500.00") and by["CASH"] == Decimal("500.00")


def test_kuri_weight_derived_when_showwgt():
    db, svc = make()
    svc.collect([{"code": "SCH001", "amount": "6000", "showwgt": "Y"}], "2026-06-17", "CASH", "6000")
    wgt = db.scalar("SELECT wgt FROM kuricolln WHERE code = 'SCH001'")
    assert Decimal(str(wgt)) == Decimal("1.000")    # 6000 / 6000


def test_kuri_requires_rows():
    _, svc = make()
    with pytest.raises(KuriError, match="No rows"):
        svc.collect([], "2026-06-17")


def test_smith_book_weight_balance():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE smithm (slno INT, docno TEXT, tdate TEXT, smithcode TEXT, netamt NUM, rate NUM, tmcharge NUM, control INT)"))
        c.execute(text("CREATE TABLE smithd (slno INT, weight NUM, givrec TEXT)"))
        c.execute(text("INSERT INTO smithm VALUES (1,'D1','2026-06-10','SM1',0,0,0,1)"))
        c.execute(text("INSERT INTO smithd VALUES (1, 100, 'G')"))   # issued 100
        c.execute(text("INSERT INTO smithd VALUES (1, 30, 'R')"))    # received 30
    db.table_exists = lambda t: t in ("smithm", "smithd")
    res = SmithBookService(db).transactions("SM1", "2026-06-01", "2026-06-30")
    assert res["issued"] == Decimal("100.000")
    assert res["received"] == Decimal("30.000")
    assert res["balance"] == Decimal("70.000")
