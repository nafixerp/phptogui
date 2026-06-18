"""Bucket A misc: non-transactional days + gold rate history."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.misc_reports.service import MiscReportsService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (tdate TEXT, amount NUM)"))
        c.execute(text("CREATE TABLE smithm (tdate TEXT)"))
        c.execute(text("CREATE TABLE ratehistory (tdate TEXT, grate NUM, g18rate NUM, srate NUM, prate NUM)"))
        # activity only on 06-02 (daybook) and 06-04 (smith)
        c.execute(text("INSERT INTO daybook VALUES ('2026-06-02',100)"))
        c.execute(text("INSERT INTO smithm VALUES ('2026-06-04')"))
        c.execute(text("INSERT INTO ratehistory VALUES ('2026-06-01',6000,5000,75,3000)"))
        c.execute(text("INSERT INTO ratehistory VALUES ('2026-06-03',6100,5100,76,3050)"))
    _bind(db, {"daybook": {"tdate", "amount"}, "smithm": {"tdate"},
               "ratehistory": {"tdate", "grate", "g18rate", "srate", "prate"}})
    return db


def test_non_transactional_days():
    rows = MiscReportsService(make_db()).non_transactional_days("2026-06-01", "2026-06-05")
    days = {r["tdate"] for r in rows}
    # active: 06-02, 06-04 -> holidays: 06-01, 06-03, 06-05
    assert days == {"2026-06-01", "2026-06-03", "2026-06-05"}
    assert rows[0]["sno"] == 1 and rows[-1]["sno"] == 3


def test_gold_rate_history():
    rows = MiscReportsService(make_db()).gold_rate_history("2026-06-01", "2026-06-30")
    # ordered DESC by date
    assert rows[0]["tdate"] == "2026-06-03"
    assert rows[0]["grate"] == Decimal("6100.00")
    assert rows[1]["srate"] == Decimal("75.00")
