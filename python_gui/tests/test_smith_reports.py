"""Bucket A smith: transaction summary + W&A summary."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.smith_reports.service import SmithReportsService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, ctype TEXT)"))
        c.execute(text("CREATE TABLE clientsgs (code TEXT)"))
        c.execute(text("CREATE TABLE smithm (slno INT, smithcode TEXT, control INT, tdate TEXT)"))
        c.execute(text("CREATE TABLE smithd (slno INT, givrec TEXT, netwgt NUM, wastage NUM, mcharge NUM, stoneprice NUM)"))
        c.execute(text("CREATE TABLE daybook (accode TEXT, amount NUM, control INT, tdate TEXT)"))
        c.execute(text("INSERT INTO clients VALUES ('S1','Smith One','G')"))
        c.execute(text("INSERT INTO clientsgs VALUES ('S1')"))
        c.execute(text("INSERT INTO smithm VALUES (1,'S1',1,'2026-06-10')"))  # issue
        c.execute(text("INSERT INTO smithm VALUES (2,'S1',1,'2026-06-20')"))  # receive
        c.execute(text("INSERT INTO smithd VALUES (1,'G',100.0,0,0,0)"))
        c.execute(text("INSERT INTO smithd VALUES (2,'R',60.0,2.5,500,300)"))
        c.execute(text("INSERT INTO daybook VALUES ('S1',-1000,1,'2026-06-15')"))  # paid
    _bind(db, {"clients": {"code", "name", "ctype"}, "clientsgs": {"code"},
               "smithm": {"slno", "smithcode", "control", "tdate"},
               "smithd": {"slno", "givrec", "netwgt", "wastage", "mcharge", "stoneprice"},
               "daybook": {"accode", "amount", "control", "tdate"}})
    return db


def test_smith_trans_summary():
    rows = SmithReportsService(make_db()).trans_summary("2026-06-01", "2026-06-30")
    assert len(rows) == 1
    r = rows[0]
    assert r["issuedwgt"] == Decimal("100.000") and r["rcvdwgt"] == Decimal("60.000")
    assert r["pendwgt"] == Decimal("40.000")
    assert r["wastage"] == Decimal("2.500")
    assert r["mcstamt"] == Decimal("800.00")   # mcharge 500 + stone 300
    assert r["paidamt"] == Decimal("1000.00")  # abs(-1000)


def test_smith_wa_summary():
    rows = SmithReportsService(make_db()).wa_summary("2026-06-30")
    r = rows[0]
    assert r["pendwgt"] == Decimal("40.000")
    assert r["lastissue"] == "2026-06-10"
    assert r["tranamt"] == Decimal("-1000.00")
