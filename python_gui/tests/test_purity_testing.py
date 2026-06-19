"""Pending: purity testing (testdet record CRUD)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.purity_testing.service import PurityTestingError, PurityTestingService

sqlite3.register_adapter(Decimal, str)

_COLS = {"slno", "docno", "tdate", "customer", "purityinperc", "purityinct", "rcvdon",
         "testedon", "otherinfo", "rcvdwgt", "typeofsample", "control"}


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE testdet (slno INT, docno TEXT, tdate TEXT, customer TEXT, purityinperc NUM, "
                       "purityinct NUM, rcvdon TEXT, testedon TEXT, otherinfo TEXT, rcvdwgt NUM, typeofsample TEXT, control INT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    db.table_exists = lambda t: t in {"testdet", "generali"}
    db.column_exists = lambda t, c: c in _COLS if t == "testdet" else True
    db.columns = lambda t: _COLS if t == "testdet" else {"code", "cvalue"}
    return db


def test_save_new_reserves_slno_and_billno():
    db = make_db(); svc = PurityTestingService(db)
    res = svc.save({"docno": "1001", "customer": "ACME", "purityinperc": 91.6, "rcvdwgt": 12.5, "typeofsample": "Ring"})
    assert res["slno"] == 1 and res["updated"] is False
    row = db.fetchone("SELECT customer, purityinperc FROM testdet WHERE slno=1")
    assert row["customer"] == "ACME"
    assert Decimal(str(row["purityinperc"])) == Decimal("91.600")
    # BILLNO set to docno, SLNO advanced
    assert int(db.scalar("SELECT cvalue FROM generali WHERE code='BILLNO'")) == 1001
    assert int(db.scalar("SELECT cvalue FROM generali WHERE code='SLNO'")) == 1
    # next record gets slno 2
    assert svc.save({"customer": "BETA"})["slno"] == 2


def test_edit_updates_existing():
    db = make_db(); svc = PurityTestingService(db)
    r = svc.save({"customer": "ACME", "rcvdwgt": 10})
    svc.save({"customer": "ACME RENAMED", "rcvdwgt": 20}, edit_slno=r["slno"])
    assert db.scalar("SELECT customer FROM testdet WHERE slno=:s", {"s": r["slno"]}) == "ACME RENAMED"
    assert int(db.scalar("SELECT COUNT(*) FROM testdet")) == 1


def test_customer_required():
    with pytest.raises(PurityTestingError):
        PurityTestingService(make_db()).save({"customer": ""})
