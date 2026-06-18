"""Pending reports: kuri finish/interest + order profit analysis."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.kuri_reports.service import KuriReportsService
from python_gui.modules.order_profit.service import OrderProfitService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


# ── kuri reports ─────────────────────────────────────────────────────────────

def make_kuri_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, grp TEXT)"))
        c.execute(text("CREATE TABLE clients_kuridet (code TEXT, name TEXT, totamt NUM, bonus NUM, collnopbal NUM, "
                       "kuritype TEXT, finished TEXT, intrate NUM)"))
        c.execute(text("CREATE TABLE kuricolln (code TEXT, tdate TEXT, amount NUM, control INT)"))
        c.execute(text("INSERT INTO clients VALUES ('K1','Member One','KC')"))
        c.execute(text("INSERT INTO clients VALUES ('K2','Member Two','KC')"))
        c.execute(text("INSERT INTO clients_kuridet VALUES ('K1','Member One',11000,1000,500,'G1','N',12)"))
        c.execute(text("INSERT INTO clients_kuridet VALUES ('K2','Member Two',11000,1000,0,'G1','Y',12)"))  # finished
        c.execute(text("INSERT INTO kuricolln VALUES ('K1','2025-06-20',4000,1)"))  # ~1yr before cutoff
        c.execute(text("INSERT INTO kuricolln VALUES ('K1','2026-06-20',1000,1)"))  # same day -> 0 days
    _bind(db, {"clients": {"code", "name", "grp"},
               "clients_kuridet": {"code", "name", "totamt", "bonus", "collnopbal", "kuritype", "finished", "intrate"},
               "kuricolln": {"code", "tdate", "amount", "control"}})
    return db


def test_kuri_finish_list():
    rows = KuriReportsService(make_kuri_db()).finish_list("2026-06-20", grate=5000)
    # only unfinished (K1)
    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == "K1"
    # collected = 4000 + 1000 + opbal 500 = 5500
    assert r["tcolln"] == Decimal("5500.00")
    assert r["balance"] == Decimal("5500.00")  # 11000 - 5500
    assert r["estwgt"] == Decimal("2.200")  # 11000 / 5000


def test_kuri_interest_list():
    rows = KuriReportsService(make_kuri_db()).interest_list("2026-06-20")
    by = {r["code"]: r for r in rows}
    # K1: 4000 @12% for 365 days = 480 ; the same-day 1000 contributes 0
    assert by["K1"]["intamt"] == Decimal("480.00")
    # K2 finished but still KC group -> intrate 12, but no collections -> 0
    assert by["K2"]["intamt"] == Decimal("0.00")


# ── order profit ─────────────────────────────────────────────────────────────

def make_order_profit_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE salesm (slno INT, tdate TEXT, billno TEXT, orderno TEXT, custname TEXT, billamt NUM, grate NUM, control INT)"))
        c.execute(text("CREATE TABLE salesd (slno INT, weight NUM, stonewgt NUM, mcharge NUM, stoneprice NUM)"))
        c.execute(text("CREATE TABLE orderm (ordno TEXT, advance NUM, sretamt NUM, eamt NUM, gadvance NUM, rate NUM)"))
        c.execute(text("CREATE TABLE advafter (ordno TEXT, amount NUM, rate NUM)"))
        c.execute(text("INSERT INTO salesm VALUES (1,'2026-06-10','S1','OR1','ACME',100000,5000,1)"))
        c.execute(text("INSERT INTO salesm VALUES (2,'2026-06-11','S2','','WALKIN',5000,5000,1)"))  # no order -> excluded
        c.execute(text("INSERT INTO salesd VALUES (1,20.0,2.0,3000,1000)"))
        c.execute(text("INSERT INTO orderm VALUES ('OR1',10000,0,0,1.0,5000)"))  # advamt1=10000, advwgt1= 1 + 10000/5000=3
        c.execute(text("INSERT INTO advafter VALUES ('OR1',5000,5000)"))  # advamt2=5000, advwgt2=1
    _bind(db, {"salesm": {"slno", "tdate", "billno", "orderno", "custname", "billamt", "grate", "control"},
               "salesd": {"slno", "weight", "stonewgt", "mcharge", "stoneprice"},
               "orderm": {"ordno", "advance", "sretamt", "eamt", "gadvance", "rate"},
               "advafter": {"ordno", "amount", "rate"}})
    return db


def test_order_profit_diff():
    res = OrderProfitService(make_order_profit_db()).report("2026-06-01", "2026-06-30")
    assert res["totals"]["count"] == 1
    r = res["rows"][0]
    assert r["totadvamt"] == Decimal("15000.00")  # 10000 + 5000
    assert r["totadvwgt"] == Decimal("4.000")     # 3 + 1
    assert r["totsoldamt"] == Decimal("96000.00")  # 100000 - (3000+1000)
    assert r["totsoldwgt"] == Decimal("18.000")    # 20 - 2
    # diff = (18 - 4)*5000 + 15000 - 96000 = 70000 - 81000 = -11000
    assert r["diff"] == Decimal("-11000.00")
