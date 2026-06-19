"""Bucket B tail: change due-date + other-items master."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.change_duedate.service import ChangeDuedateError, ChangeDuedateService
from python_gui.modules.other_items.service import OtherItemsError, OtherItemsService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


# ── change due-date ──────────────────────────────────────────────────────────

def make_dd_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, duedate TEXT)"))
        c.execute(text("INSERT INTO clients VALUES ('C1','ACME','2026-06-01')"))
    _bind(db, {"clients": {"code", "name", "duedate"}})
    return db


def test_change_duedate_updates():
    db = make_dd_db(); svc = ChangeDuedateService(db)
    assert svc.party("c1")["duedate"] == "2026-06-01"
    svc.save("c1", "2026-09-30")
    assert db.scalar("SELECT duedate FROM clients WHERE code='C1'") == "2026-09-30"


def test_change_duedate_validations():
    db = make_dd_db(); svc = ChangeDuedateService(db)
    with pytest.raises(ChangeDuedateError):
        svc.save("", "2026-09-30")
    with pytest.raises(ChangeDuedateError):
        svc.save("C1", "")
    with pytest.raises(ChangeDuedateError):
        svc.save("ZZZ", "2026-09-30")  # no such party


# ── other items master ──────────────────────────────────────────────────────

def make_oi_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE itemsothers (code TEXT, name TEXT, grp TEXT, srate NUM, prate NUM, cost NUM, opcost NUM, opstock INT, stock INT, keepstk INT)"))
    _bind(db, {"itemsothers": {"code", "name", "grp", "srate", "prate", "cost", "opcost", "opstock", "stock", "keepstk"}})
    return db


def test_other_items_add_edit_delete():
    db = make_oi_db(); svc = OtherItemsService(db)
    svc.add({"code": "box1", "name": "gift box", "srate": 100, "cost": 60, "stock": 10})
    row = svc.list()[0]
    assert row["code"] == "BOX1" and row["name"] == "GIFT BOX"
    assert Decimal(str(row["srate"])) == Decimal("100.00")
    # duplicate rejected
    with pytest.raises(OtherItemsError):
        svc.add({"code": "BOX1", "name": "dup"})
    # edit
    svc.edit({"code": "BOX1", "name": "velvet box", "srate": 150, "cost": 70, "stock": 5})
    assert db.scalar("SELECT name FROM itemsothers WHERE code='BOX1'") == "VELVET BOX"
    assert Decimal(str(db.scalar("SELECT srate FROM itemsothers WHERE code='BOX1'"))) == Decimal("150.00")
    # delete
    svc.delete("box1")
    assert svc.list() == []


def test_other_items_requires_code():
    db = make_oi_db()
    with pytest.raises(OtherItemsError):
        OtherItemsService(db).add({"code": "", "name": "x"})
