"""Bucket A sales-misc: delivery status + VA check list."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.sales_misc_reports.service import SalesMiscReportsService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE salesm (slno INT, tdate TEXT, billno TEXT, custname TEXT, billamt NUM, eamt NUM, "
                       "sretamt NUM, discount NUM, smcode TEXT, dstatus TEXT, control INT, opbill INT)"))
        c.execute(text("CREATE TABLE salesd (slno INT, code TEXT, weight NUM, stonewgt NUM, wastage NUM, mcharge NUM, rate NUM, stoneprice NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, itype TEXT)"))
        c.execute(text("INSERT INTO salesm VALUES (1,'2026-06-10','S1','ACME',10000,1000,0,500,'SM1','D',1,0)"))
        c.execute(text("INSERT INTO salesm VALUES (2,'2026-06-11','S2','BETA',5000,0,0,0,'SM1','P',1,0)"))
        c.execute(text("INSERT INTO items VALUES ('R1','G')"))
        c.execute(text("INSERT INTO salesd VALUES (1,'R1',10.0,2.0,1.0,3000,5000,500)"))  # gold net wt 8
        c.execute(text("INSERT INTO salesd VALUES (2,'R1',5.0,1.0,0.5,1500,5000,0)"))
    _bind(db, {"salesm": {"slno", "tdate", "billno", "custname", "billamt", "eamt", "sretamt", "discount", "smcode", "dstatus", "control", "opbill"},
               "salesd": {"slno", "code", "weight", "stonewgt", "wastage", "mcharge", "rate", "stoneprice"},
               "items": {"code", "itype"}})
    return db


def test_delivery_status_balance_and_gold():
    svc = SalesMiscReportsService(make_db())
    rows = svc.delivery_status("2026-06-01", "2026-06-30")
    by = {r["billno"]: r for r in rows}
    # S1 balance = 10000 - 1000(eamt) - 0 - 500(disc) = 8500
    assert by["S1"]["balance"] == Decimal("8500.00")
    assert by["S1"]["goldwgt"] == Decimal("8.000")  # 10 - 2 stone
    # pending filter -> only S2
    pend = svc.delivery_status("2026-06-01", "2026-06-30", reptype="pending")
    assert {r["billno"] for r in pend} == {"S2"}


def test_va_check_totals():
    v = SalesMiscReportsService(make_db()).va_check("2026-06-01", "2026-06-30")
    # vaamt = (3000 + 1*5000) + (1500 + 0.5*5000) = 8000 + 4000 = 12000
    assert v["vaamt"] == Decimal("12000.00")
    assert v["mcharge"] == Decimal("4500.00")
    assert v["disc"] == Decimal("500.00")
    # tvaperc = (3000/10/5000*100) + (1500/5/5000*100) = 6 + 6 = 12
    assert v["tvaperc"] == Decimal("12.00")
