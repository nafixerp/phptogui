"""Bucket B: rate-difference adjustment (two-line journal, zero-sum)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.rate_diff.service import RateDiffError, RateDiffService

sqlite3.register_adapter(Decimal, str)

_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP = {"slno", "vchno", "particular", "ic", "uid", "tdate"}
_COL = {"slno", "code", "tdate", "billno", "tranamt", "discount", "control", "islno", "grate", "grate2"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, ic TEXT, uid TEXT, tdate TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE collection (slno INT, code TEXT, tdate TEXT, billno TEXT, tranamt NUM, discount NUM, control INT, islno INT, grate NUM, grate2 NUM)"))
    pe = PostingEngine(db)
    tabs = {"daybook", "daybookpart", "generali", "collection"}
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: (c in _DB) if t == "daybook" else (c in _DP) if t == "daybookpart" else (c in _COL) if t == "collection" else True
    pe.db.columns = lambda t: _DB if t == "daybook" else _DP if t == "daybookpart" else _COL if t == "collection" else set()
    return db, pe


def _rows(db, slno):
    return db.fetchall("SELECT accode, amount FROM daybook WHERE slno = :s ORDER BY rowid", {"s": slno})


def test_rate_diff_two_line_zero_sum():
    db, pe = make_engine()
    res = RateDiffService(pe, control=1).save(tdate="2026-06-17", code="C1", diffamt=1500, weight=10, newrate=6150)
    assert res["balanced"] is True
    assert res["docno"].startswith("JLB/")
    rows = {r["accode"]: r["amount"] for r in _rows(db, res["slno"])}
    assert rows["RDIFF"] == Decimal("1500.00")
    assert rows["C1"] == Decimal("-1500.00")


def test_rate_diff_bill_writes_collection():
    db, pe = make_engine()
    res = RateDiffService(pe, control=1).save(tdate="2026-06-17", code="C1", diffamt=800,
                                              billno="S100", islno=42, newrate=6000)
    n = int(db.scalar("SELECT COUNT(*) FROM collection WHERE slno = :s", {"s": res["slno"]}))
    assert n == 1
    assert db.scalar("SELECT tranamt FROM collection WHERE slno = :s", {"s": res["slno"]}) == "-800.00" \
        or Decimal(str(db.scalar("SELECT tranamt FROM collection WHERE slno = :s", {"s": res["slno"]}))) == Decimal("-800.00")


def test_rate_diff_control2_voucher_series():
    db, pe = make_engine()
    res = RateDiffService(pe, control=2).save(tdate="2026-06-17", code="C1", diffamt=500)
    assert res["docno"].startswith("JLE/")


def test_rate_diff_rejects_zero():
    db, pe = make_engine()
    with pytest.raises(RateDiffError):
        RateDiffService(pe).save(tdate="2026-06-17", code="C1", diffamt=0)
