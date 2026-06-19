"""Pending: group amount allocation (one-to-many zero-sum journal)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.group_amt_allocation.service import (
    GroupAmtAllocationError,
    GroupAmtAllocationService,
)

sqlite3.register_adapter(Decimal, str)

_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP = {"slno", "vchno", "particular", "ic", "uid", "tdate"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, ic TEXT, uid TEXT, tdate TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    cmap = {"daybook": _DB, "daybookpart": _DP, "generali": {"code", "cvalue"}}
    tabs = set(cmap)
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: c in cmap.get(t, set())
    pe.db.columns = lambda t: cmap.get(t, set())
    return db, pe


def _rows(db, slno):
    return db.fetchall("SELECT accode, amount FROM daybook WHERE slno=:s ORDER BY rowid", {"s": slno})


def test_allocation_credited_zero_sum():
    db, pe = make_engine()
    res = GroupAmtAllocationService(pe, control=1).save(
        tdate="2026-06-17", opac="cash", credited=True,
        items=[{"accode": "EXP1", "amount": 300}, {"accode": "EXP2", "amount": 200}])
    assert res["balanced"] and res["docno"].startswith("JLB/")
    assert res["total"] == Decimal("500.00")
    rows = {r["accode"]: r["amount"] for r in _rows(db, res["slno"])}
    assert rows["EXP1"] == Decimal("300.00") and rows["EXP2"] == Decimal("200.00")
    assert rows["CASH"] == Decimal("-500.00")  # opposite absorbs negated total
    assert sum(r["amount"] for r in [{"amount": Decimal(str(v["amount"]))} for v in _rows(db, res["slno"])]) == Decimal("0.00")


def test_allocation_debited_flips_signs():
    db, pe = make_engine()
    res = GroupAmtAllocationService(pe, control=1).save(
        tdate="2026-06-17", opac="CASH", credited=False,
        items=[{"accode": "EXP1", "amount": 400}])
    rows = {r["accode"]: r["amount"] for r in _rows(db, res["slno"])}
    assert rows["EXP1"] == Decimal("-400.00") and rows["CASH"] == Decimal("400.00")


def test_allocation_validations():
    db, pe = make_engine()
    svc = GroupAmtAllocationService(pe)
    with pytest.raises(GroupAmtAllocationError):
        svc.save(tdate="", opac="CASH", items=[{"accode": "E", "amount": 1}])
    with pytest.raises(GroupAmtAllocationError):
        svc.save(tdate="2026-06-17", opac="", items=[{"accode": "E", "amount": 1}])
    with pytest.raises(GroupAmtAllocationError):
        svc.save(tdate="2026-06-17", opac="CASH", items=[{"accode": "E", "amount": 0}])
