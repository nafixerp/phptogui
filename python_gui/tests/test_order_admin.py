"""Phase 8: order rate-fix / block / unblock + order process & returns reports."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.order_admin.service import OrderAdminError, OrderAdminService
from python_gui.modules.order_reports.service import OrderReportsService

sqlite3.register_adapter(Decimal, str)

_OM = {"slno", "ordno", "tdate", "custcode", "custname", "duedate", "billamt",
       "advance", "eamt", "sretamt", "status", "control", "blocked", "note", "salebill", "smcode"}


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE orderm (slno INT, ordno TEXT, tdate TEXT, custcode TEXT, custname TEXT, duedate TEXT, "
                       "billamt NUM, advance NUM, eamt NUM, sretamt NUM, status INT, control INT, blocked TEXT, note TEXT, salebill TEXT, smcode TEXT)"))
        c.execute(text("CREATE TABLE clients (code TEXT, mobile TEXT)"))
        c.execute(text("CREATE TABLE salesm (billno TEXT, tdate TEXT, billamt NUM)"))
        c.execute(text("INSERT INTO orderm VALUES (1,'OR1','2026-06-01','C1','ACME','2026-06-30',10000,2000,500,300,1,1,'N','','SB1','SM1')"))
        c.execute(text("INSERT INTO orderm VALUES (2,'OR2','2026-06-02','C2','BETA','2026-06-30',5000,1000,0,0,2,1,'N','','','SM1')"))  # returned
        c.execute(text("INSERT INTO clients VALUES ('C1','99999')"))
        c.execute(text("INSERT INTO salesm VALUES ('SB1','2026-06-20',10500)"))
    db.table_exists = lambda t: t in {"orderm", "clients", "salesm"}
    db.column_exists = lambda t, col: (col in _OM) if t == "orderm" else True
    db.columns = lambda t: _OM if t == "orderm" else set()
    return db


def test_rate_fix_sets_note():
    db = make_db(); svc = OrderAdminService(db)
    note = svc.rate_fix("or1", 5550.5)
    assert note.startswith("Rate Fixed :5550.50")
    assert str(db.scalar("SELECT note FROM orderm WHERE ordno='OR1'")).startswith("Rate Fixed :5550.50")


def test_rate_fix_rejects_returned_order():
    svc = OrderAdminService(make_db())
    with pytest.raises(OrderAdminError):
        svc.rate_fix("OR2", 5000)


def test_rate_fix_rejects_bad_rate():
    svc = OrderAdminService(make_db())
    with pytest.raises(OrderAdminError):
        svc.rate_fix("OR1", 0)


def test_block_unblock():
    db = make_db(); svc = OrderAdminService(db)
    svc.set_blocked("OR1", True)
    assert db.scalar("SELECT blocked FROM orderm WHERE ordno='OR1'") == "Y"
    svc.set_blocked("OR1", False)
    assert db.scalar("SELECT blocked FROM orderm WHERE ordno='OR1'") == "N"
    with pytest.raises(OrderAdminError):
        svc.set_blocked("OR2", True)  # returned


def test_pending_process():
    rows = OrderReportsService(make_db()).pending_process()
    # only status=1 -> OR1
    assert len(rows) == 1
    r = rows[0]
    assert r["ordno"] == "OR1"
    assert r["tadv"] == Decimal("2800.00")  # 2000 + 500 + 300
    assert r["mobile"] == "99999"


def test_order_returns():
    rows = OrderReportsService(make_db()).returns("2026-06-01", "2026-06-30")
    assert len(rows) == 1
    assert rows[0]["ordno"] == "OR1" and rows[0]["salebill"] == "SB1"
