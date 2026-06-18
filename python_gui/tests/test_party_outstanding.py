"""Bucket A party: supplier/customer outstanding balances."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.party_outstanding.service import PartyOutstandingService

sqlite3.register_adapter(Decimal, str)


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE accountm (accode TEXT, actype2 TEXT, opbal NUM, opbalb NUM, control INT)"))
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, mobile TEXT)"))
        c.execute(text("CREATE TABLE daybook (accode TEXT, amount NUM, control INT, tdate TEXT)"))
        # supplier SUP1: opening 0, +20000 credit (payable) up to as-of
        c.execute(text("INSERT INTO accountm VALUES ('SUP1','S',0,0,1)"))
        c.execute(text("INSERT INTO accountm VALUES ('CUS1','C',0,0,1)"))
        c.execute(text("INSERT INTO accountm VALUES ('ZERO','S',0,0,1)"))  # zero balance -> dropped
        c.execute(text("INSERT INTO clients VALUES ('SUP1','Supplier One','111')"))
        c.execute(text("INSERT INTO clients VALUES ('CUS1','Customer One','222')"))
        c.execute(text("INSERT INTO daybook VALUES ('SUP1',20000,1,'2026-06-10')"))   # payable (positive=TG)
        c.execute(text("INSERT INTO daybook VALUES ('CUS1',-8000,1,'2026-06-10')"))   # receivable (negative=TR)
        c.execute(text("INSERT INTO daybook VALUES ('SUP1',5000,1,'2026-07-15')"))    # after as-of -> excluded
    db.table_exists = lambda t: t in {"accountm", "clients", "daybook"}
    db.column_exists = lambda t, col: True
    db.columns = lambda t: set()
    return db


def test_supplier_outstanding():
    res = PartyOutstandingService(make_db()).outstanding("Supplier", "2026-06-30")
    by = {r["accode"]: r for r in res["rows"]}
    assert "ZERO" not in by  # zero balance dropped
    assert by["SUP1"]["status"] == "TG"  # payable
    assert by["SUP1"]["bal_abs"] == Decimal("20000.00")  # July entry excluded
    assert res["totals"]["tg"] == Decimal("20000.00")


def test_customer_outstanding():
    res = PartyOutstandingService(make_db()).outstanding("Customer", "2026-06-30")
    by = {r["accode"]: r for r in res["rows"]}
    assert by["CUS1"]["status"] == "TR"  # receivable
    assert by["CUS1"]["bal_abs"] == Decimal("8000.00")
    assert res["totals"]["tr"] == Decimal("8000.00")
