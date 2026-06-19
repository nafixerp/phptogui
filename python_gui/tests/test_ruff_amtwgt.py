"""Bucket B tail: ruff work grid + amount/weight transfer journal."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.amt_wgt_transfer.service import AmtWgtTransferError, AmtWgtTransferService
from python_gui.modules.ruff_work.service import RuffWorkService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


# ── ruff work ────────────────────────────────────────────────────────────────

_RW = {"slno", "party", "tdate", "item", "amount", "part", "pend", "number", "control", "inexp", "sman", "person", "weight", "qty"}


def make_rw_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE ruffwrk (slno INTEGER PRIMARY KEY AUTOINCREMENT, party TEXT, tdate TEXT, item TEXT, "
                       "amount TEXT, part TEXT, pend INT, number INT, control INT, inexp TEXT, sman TEXT, person TEXT, weight TEXT, qty TEXT)"))
    _bind(db, {"ruffwrk": _RW})
    return db


def test_ruff_work_insert_update_delete():
    db = make_rw_db(); svc = RuffWorkService(db)
    svc.save([{"party": "smith one", "item": "ring", "weight": "10.5", "amount": "5000"}])
    rows = svc.list()
    assert len(rows) == 1 and rows[0]["party"] == "smith one"
    sno = rows[0]["slno"]
    # update
    svc.save([{"slno": sno, "party": "smith one", "item": "chain", "weight": "20"}])
    assert db.scalar("SELECT item FROM ruffwrk WHERE slno=:s", {"s": sno}) == "chain"
    # blank party on existing row -> delete
    svc.save([{"slno": sno, "party": ""}])
    assert svc.list() == []


# ── amount/weight transfer ───────────────────────────────────────────────────

_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP = {"slno", "vchno", "particular", "ic", "uid"}
_DRW = {"slno", "rate", "mcp", "wgt", "code", "tdate", "control"}


def make_awt_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, ic TEXT, uid TEXT)"))
        c.execute(text("CREATE TABLE daybookratewgt (slno INT, rate NUM, mcp NUM, wgt NUM, code TEXT, tdate TEXT, control INT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    cmap = {"daybook": _DB, "daybookpart": _DP, "daybookratewgt": _DRW, "generali": {"code", "cvalue"}}
    tabs = set(cmap)
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: c in cmap.get(t, set())
    pe.db.columns = lambda t: cmap.get(t, set())
    return db, pe


def _rows(db, slno):
    return db.fetchall("SELECT accode, amount FROM daybook WHERE slno=:s ORDER BY rowid", {"s": slno})


def test_amt_to_wgt_zero_sum():
    db, pe = make_awt_engine()
    res = AmtWgtTransferService(pe, control=1).save(
        tdate="2026-06-17", code="c1", amt=60000, weight=10.0, rate=6000, ttype="Amt To Wgt")
    assert res["balanced"] and res["docno"].startswith("JLB/")
    rows = {r["accode"]: r["amount"] for r in _rows(db, res["slno"])}
    assert rows["ATOW"] == Decimal("-60000.00") and rows["C1"] == Decimal("60000.00")
    # weight entry negative for Amt->Wgt
    assert Decimal(str(db.scalar("SELECT wgt FROM daybookratewgt WHERE slno=:s", {"s": res["slno"]}))) == Decimal("-10.000")


def test_wgt_to_amt_signs_flip():
    db, pe = make_awt_engine()
    res = AmtWgtTransferService(pe, control=1).save(
        tdate="2026-06-17", code="C1", amt=60000, weight=10.0, rate=6000, ttype="Wgt To Amt")
    rows = {r["accode"]: r["amount"] for r in _rows(db, res["slno"])}
    assert rows["ATOW"] == Decimal("60000.00") and rows["C1"] == Decimal("-60000.00")
    assert Decimal(str(db.scalar("SELECT wgt FROM daybookratewgt WHERE slno=:s", {"s": res["slno"]}))) == Decimal("10.000")


def test_amt_wgt_validations():
    db, pe = make_awt_engine()
    svc = AmtWgtTransferService(pe)
    with pytest.raises(AmtWgtTransferError):
        svc.save(tdate="", code="C1", amt=1, weight=1)
    with pytest.raises(AmtWgtTransferError):
        svc.save(tdate="2026-06-17", code="C1", amt=0, weight=10)
