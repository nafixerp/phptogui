"""Pending: remake report (repair-return details)."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.remake_report.service import RemakeReportService

sqlite3.register_adapter(Decimal, str)

_RM = {"slno", "billno", "tdate", "custcode", "custname", "rbillno", "sman", "givrec", "amount", "discount", "rcvd", "taxamt"}
_RD = {"slno", "sno", "code", "name", "qty", "weight", "stonewgt", "netwgt"}


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE repairm (slno INT, billno TEXT, tdate TEXT, custcode TEXT, custname TEXT, rbillno TEXT, "
                       "sman TEXT, givrec TEXT, amount NUM, discount NUM, rcvd NUM, taxamt NUM)"))
        c.execute(text("CREATE TABLE repaird (slno INT, sno INT, code TEXT, name TEXT, qty INT, weight NUM, stonewgt NUM, netwgt NUM)"))
        c.execute(text("INSERT INTO repairm VALUES (1,'RM1','2026-06-10','C1','ACME','RB1','SM1','G',5000,0,2000,150)"))
        c.execute(text("INSERT INTO repairm VALUES (2,'RM2','2026-06-12','C2','BETA','','SM1','R',3000,0,0,0)"))  # givrec R -> excluded
        c.execute(text("INSERT INTO repaird VALUES (1,1,'R1','Ring',1,8.0,1.0,7.0)"))
        c.execute(text("INSERT INTO repaird VALUES (1,2,'R2','Chain',1,12.0,0,12.0)"))
    db.table_exists = lambda t: t in {"repairm", "repaird"}
    db.column_exists = lambda t, c: (c in _RM) if t == "repairm" else (c in _RD)
    db.columns = lambda t: _RM if t == "repairm" else _RD
    return db


def test_remake_report_only_givrec_g():
    rows = RemakeReportService(make_db()).report("2026-06-01", "2026-06-30")
    assert len(rows) == 1
    r = rows[0]
    assert r["billno"] == "RM1"
    # net = amount + tax - discount = 5000 + 150 - 0 = 5150 ; balance = 5150 - 2000
    assert r["netamt"] == Decimal("5150.00")
    assert r["balance"] == Decimal("3150.00")
    assert r["item_count"] == 2
    assert r["tot_wgt"] == Decimal("20.000")
