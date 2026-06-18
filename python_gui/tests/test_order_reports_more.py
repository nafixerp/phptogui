"""Bucket A orders: pending register + advance report (order_reports extras)."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.order_reports.service import OrderReportsService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE orderm (slno INT, ordno TEXT, tdate TEXT, duedate TEXT, custcode TEXT, custname TEXT, "
                       "smcode TEXT, advance NUM, eamt NUM, sretamt NUM, gadvance NUM, status INT, control INT)"))
        c.execute(text("CREATE TABLE orderd (slno INT, code TEXT, qty INT, weight NUM, stonewgt NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE advafter (slno INT, amount NUM)"))
        c.execute(text("INSERT INTO orderm VALUES (1,'OR1','2026-06-01','2026-06-30','C1','ACME','SM1',2000,500,300,1.5,1,1)"))
        c.execute(text("INSERT INTO orderm VALUES (2,'OR2','2026-06-05','2026-06-30','C2','BETA','SM1',1000,0,0,0,2,1)"))  # returned
        c.execute(text("INSERT INTO orderd VALUES (1,'R1',2,12.0,2.0)"))
        c.execute(text("INSERT INTO items VALUES ('R1','Gold Ring')"))
        c.execute(text("INSERT INTO advafter VALUES (1,1500)"))
    _bind(db, {"orderm": {"slno", "ordno", "tdate", "duedate", "custcode", "custname", "smcode", "advance", "eamt", "sretamt", "gadvance", "status", "control"},
               "orderd": {"slno", "code", "qty", "weight", "stonewgt"},
               "items": {"code", "name"}, "advafter": {"slno", "amount"}})
    return db


def test_pending_register_item_level():
    rows = OrderReportsService(make_db()).pending_register()
    # only status=1 order OR1's item
    assert len(rows) == 1
    r = rows[0]
    assert r["ordno"] == "OR1" and r["itemname"] == "Gold Ring"
    assert r["weight"] == Decimal("12.000")


def test_advance_report_totals_with_advafter():
    res = OrderReportsService(make_db()).advance_report("2026-06-01", "2026-06-30")
    by = {r["ordno"]: r for r in res["rows"]}
    # OR1 totadv = 2000 + 500 + 300 + 1500(advafter) = 4300
    assert by["OR1"]["advaft"] == Decimal("1500.00")
    assert by["OR1"]["totadv"] == Decimal("4300.00")
    # OR2 has no advafter -> totadv = 1000
    assert by["OR2"]["totadv"] == Decimal("1000.00")
    assert res["totals"]["totadv"] == Decimal("5300.00")


def test_advance_report_pending_filter():
    res = OrderReportsService(make_db()).advance_report("2026-06-01", "2026-06-30", filter_="Pending")
    assert {r["ordno"] for r in res["rows"]} == {"OR1"}
