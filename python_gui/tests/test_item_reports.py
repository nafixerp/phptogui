"""Bucket A items: itemwise profit, item movement, cost list."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.item_reports.service import ItemReportsService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT, itype TEXT, cost NUM, rate NUM, stkinnos TEXT, disabled INT)"))
        c.execute(text("CREATE TABLE salesm (slno INT, tdate TEXT, control INT, sr TEXT, opbill INT)"))
        c.execute(text("CREATE TABLE salesd (slno INT, code TEXT, qty INT, weight NUM, amount NUM, cost NUM)"))
        # R1 weight-costed (stkinnos N), R2 qty-costed (stkinnos Y)
        c.execute(text("INSERT INTO items VALUES ('R1','Gold Ring','G',5000,6000,'N',0)"))
        c.execute(text("INSERT INTO items VALUES ('R2','Diamond','O',2000,2500,'Y',0)"))
        c.execute(text("INSERT INTO salesm VALUES (1,'2026-06-10',1,'S',0)"))
        c.execute(text("INSERT INTO salesd VALUES (1,'R1',1,10.0,80000,5000)"))   # cost*wgt = 50000
        c.execute(text("INSERT INTO salesd VALUES (1,'R2',3,1.5,9000,2000)"))     # cost*qty = 6000
        # an opening bill (opbill=1) must be excluded
        c.execute(text("INSERT INTO salesm VALUES (2,'2026-06-11',1,'S',1)"))
        c.execute(text("INSERT INTO salesd VALUES (2,'R1',1,5.0,40000,5000)"))
    _bind(db, {"items": {"code", "name", "itype", "cost", "rate", "stkinnos", "disabled"},
               "salesm": {"slno", "tdate", "control", "sr", "opbill"},
               "salesd": {"slno", "code", "qty", "weight", "amount", "cost"}})
    return db


def test_itemwise_profit_cost_basis():
    res = ItemReportsService(make_db()).itemwise_profit("2026-06-01", "2026-06-30")
    by = {r["code"]: r for r in res["rows"]}
    # R1 weight-costed: cost = 5000*10 = 50000, profit = 80000-50000 = 30000
    assert by["R1"]["costamt"] == Decimal("50000.00")
    assert by["R1"]["profit"] == Decimal("30000.00")
    # R2 qty-costed: cost = 2000*3 = 6000, profit = 9000-6000 = 3000
    assert by["R2"]["costamt"] == Decimal("6000.00")
    assert by["R2"]["profit"] == Decimal("3000.00")
    # opbill=1 sale excluded -> R1 weight is only 10, not 15
    assert by["R1"]["twgt"] == Decimal("10.000")
    assert res["totals"]["profit"] == Decimal("33000.00")


def test_item_movement_excludes_opbill():
    rows = ItemReportsService(make_db()).item_movement("2026-06-01", "2026-06-30")
    by = {r["icode"]: r for r in rows}
    assert by["R1"]["tot_amt"] == Decimal("80000.00")  # opening bill excluded
    assert by["R2"]["tot_qty"] == 3


def test_cost_list():
    rows = ItemReportsService(make_db()).cost_list()
    by = {r["code"]: r for r in rows}
    assert by["R1"]["cost"] == Decimal("5000.00") and by["R1"]["rate"] == Decimal("6000.00")
