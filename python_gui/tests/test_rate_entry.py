"""Bucket B: daily rate entry (generald + ratehistory upsert)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.auth import AppSession
from python_gui.core.db import Database
from python_gui.modules.rate_entry.service import RateError, RateService

sqlite3.register_adapter(Decimal, str)


def make_db(seed_history=True):
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE generald (code TEXT, cvalue NUM)"))
        c.execute(text("CREATE TABLE ratehistory (tdate TEXT, ttime TEXT, grate NUM, g18rate NUM, srate NUM, prate NUM)"))
        c.execute(text("INSERT INTO generald VALUES ('GRATE',6000)"))
    db.table_exists = lambda t: t in {"generald", "ratehistory"}
    db.column_exists = lambda t, col: True
    db.columns = lambda t: {"tdate", "ttime", "grate", "g18rate", "srate", "prate"} if t == "ratehistory" else {"code", "cvalue"}
    return db


def test_save_updates_generald_and_history():
    db = make_db(); svc = RateService(db)
    svc.save({"GRATE": "6150.50", "SRATE": "78.25", "G18RATE": "5000"})
    assert Decimal(str(db.scalar("SELECT cvalue FROM generald WHERE code='GRATE'"))) == Decimal("6150.50")
    # new code inserted
    assert Decimal(str(db.scalar("SELECT cvalue FROM generald WHERE code='SRATE'"))) == Decimal("78.25")
    # ratehistory row created for today (only known columns persisted)
    n = int(db.scalar("SELECT COUNT(*) FROM ratehistory"))
    assert n == 1
    assert Decimal(str(db.scalar("SELECT grate FROM ratehistory"))) == Decimal("6150.50")


def test_save_history_upsert_same_day():
    db = make_db(); svc = RateService(db)
    svc.save({"GRATE": "6000"})
    svc.save({"GRATE": "6200"})
    # still one row for today, updated
    assert int(db.scalar("SELECT COUNT(*) FROM ratehistory")) == 1
    assert Decimal(str(db.scalar("SELECT grate FROM ratehistory"))) == Decimal("6200.00")


def test_permission_gate_blocks_save():
    db = make_db()
    blocked = AppSession(user_code="u1", user_name="U1", selected_database="demo", blocked_items={"RATESETUP"})
    svc = RateService(db, blocked)
    assert svc.can_edit() is False
    with pytest.raises(RateError):
        svc.save({"GRATE": "9999"})


def test_admin_can_edit():
    svc = RateService(make_db(), AppSession(user_code="admin", user_name="Admin", selected_database="demo", blocked_items={"RATESETUP"}))
    assert svc.can_edit() is True
