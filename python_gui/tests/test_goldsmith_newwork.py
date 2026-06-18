"""Bucket B: goldsmith new-work note (smithnewwrk grid CRUD)."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.goldsmith_newwork.service import GoldsmithNewWorkService

sqlite3.register_adapter(Decimal, str)

_COLS = {"sno", "tdate", "smithcode", "ordno", "party", "part", "status", "control", "icode", "qty", "weight", "sno2"}


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE smithnewwrk (sno INTEGER PRIMARY KEY AUTOINCREMENT, tdate TEXT, smithcode TEXT, "
                       "ordno TEXT, party TEXT, part TEXT, status INT, control INT, icode TEXT, qty INT, weight NUM, sno2 INT)"))
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("INSERT INTO clients VALUES ('S1','Smith One')"))
        c.execute(text("INSERT INTO items VALUES ('R1','Ring')"))
    db.table_exists = lambda t: t in {"smithnewwrk", "clients", "items"}
    db.column_exists = lambda t, col: True
    db.columns = lambda t: _COLS if t == "smithnewwrk" else {"code", "name"}
    return db


def test_insert_and_list():
    db = make_db(); svc = GoldsmithNewWorkService(db)
    svc.save([{"smithcode": "s1", "tdate": "2026-06-10", "icode": "r1", "qty": 2, "weight": 12.5, "status": 1}])
    rows = svc.list()
    assert len(rows) == 1
    r = rows[0]
    assert r["smithcode"] == "S1" and r["icode"] == "R1"
    assert r["smithname"] == "Smith One" and r["itemname"] == "Ring"
    assert float(r["weight"]) == 12.5


def test_blank_smithcode_row_swept():
    db = make_db(); svc = GoldsmithNewWorkService(db)
    # blank smithcode insert is ignored; a sweep removes blanks
    svc.save([{"smithcode": "", "icode": "r1", "qty": 1, "weight": 1}])
    assert svc.list() == []


def test_status_filter_and_update():
    db = make_db(); svc = GoldsmithNewWorkService(db)
    svc.save([{"smithcode": "S1", "icode": "R1", "qty": 1, "weight": 5, "status": 1}])
    sno = svc.list()[0]["sno"]
    # promote to finished (status 3)
    svc.save([{"sno": sno, "smithcode": "S1", "icode": "R1", "qty": 1, "weight": 5, "status": 3}])
    assert svc.list("pending") == []  # finished excluded from pending
    assert len(svc.list("work-finished")) == 1


def test_delete_by_blank_on_update():
    db = make_db(); svc = GoldsmithNewWorkService(db)
    svc.save([{"smithcode": "S1", "icode": "R1", "qty": 1, "weight": 5, "status": 1}])
    sno = svc.list()[0]["sno"]
    # updating an existing row with blank smithcode deletes it
    svc.save([{"sno": sno, "smithcode": "", "icode": "R1"}])
    assert svc.list() == []
