"""Pending: extra amount report (smith acid/discount extras)."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.extra_amt_report.service import ExtraAmtReportService

sqlite3.register_adapter(Decimal, str)


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE smithm (tdate TEXT, docno TEXT, smithcode TEXT, tmcharge NUM, tdsamt NUM, acidcharge NUM, discount NUM, control INT)"))
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT)"))
        c.execute(text("INSERT INTO smithm VALUES ('2026-06-10','D1','S1',5000,0,200,100,1)"))
        c.execute(text("INSERT INTO smithm VALUES ('2026-06-12','D2','S1',3000,0,0,0,1)"))  # no extra -> excluded
        c.execute(text("INSERT INTO clients VALUES ('S1','Smith One')"))
    db.table_exists = lambda t: t in {"smithm", "clients"}
    db.column_exists = lambda t, c: True
    db.columns = lambda t: set()
    return db


def test_extra_amount_rows_and_totals():
    res = ExtraAmtReportService(make_db()).report("2026-06-01", "2026-06-30")
    # only vouchers carrying an extra amount
    assert len(res["rows"]) == 1
    r = res["rows"][0]
    assert r["name"] == "Smith One"
    assert r["acidcharge"] == Decimal("200.00") and r["discount"] == Decimal("100.00")
    assert res["totals"]["acidcharge"] == Decimal("200.00")
    assert res["totals"]["discount"] == Decimal("100.00")
