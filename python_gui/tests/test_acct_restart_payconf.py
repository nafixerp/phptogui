"""Pending batch: account restart date + payment confirmation."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.auth import AppSession
from python_gui.core.db import Database
from python_gui.modules.account_restart_date.service import (
    AccountRestartDateError,
    AccountRestartDateService,
)
from python_gui.modules.payment_confirmation.service import (
    LIVE_CONTROL,
    PaymentConfirmationError,
    PaymentConfirmationService,
)

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


def make_acct_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE accountm (accode TEXT, name TEXT, opdate TEXT)"))
        c.execute(text("INSERT INTO accountm VALUES ('CASH','Cash','2026-04-01')"))
    _bind(db, {"accountm": {"accode", "name", "opdate"}})
    return db


def test_restart_date_updates():
    db = make_acct_db(); svc = AccountRestartDateService(db)
    assert svc.load("cash")["opdate"] == "2026-04-01"
    svc.save("cash", "2026-06-01")
    assert db.scalar("SELECT opdate FROM accountm WHERE accode='CASH'") == "2026-06-01"


def test_restart_date_validations():
    svc = AccountRestartDateService(make_acct_db())
    with pytest.raises(AccountRestartDateError):
        svc.save("", "2026-06-01")
    with pytest.raises(AccountRestartDateError):
        svc.save("CASH", "")
    with pytest.raises(AccountRestartDateError):
        svc.save("ZZZ", "2026-06-01")


def make_pay_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, opaccode TEXT, amount NUM, control INT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, chequeno TEXT)"))
        c.execute(text("CREATE TABLE pdclist (slno INT, control INT)"))
        c.execute(text("INSERT INTO pdclist VALUES (10, 4)"))
        c.execute(text("CREATE TABLE delpart (slno INT, tdate TEXT, part TEXT, control INT, utype TEXT, ttype TEXT, updtdate TEXT, updttime TEXT, uid TEXT, ic TEXT)"))
        # provisional payment (control 4, VP voucher, negative)
        c.execute(text("INSERT INTO daybook VALUES (10,'2026-06-10','SUP1','CASH',-5000,4)"))
        c.execute(text("INSERT INTO daybook VALUES (10,'2026-06-10','CASH','SUP1',5000,4)"))
        c.execute(text("INSERT INTO daybookpart VALUES (10,'VPB/00001','Payment to SUP1','')"))
        # a non-payment provisional (VR) must be excluded
        c.execute(text("INSERT INTO daybook VALUES (11,'2026-06-11','C1','CASH',-2000,4)"))
        c.execute(text("INSERT INTO daybookpart VALUES (11,'VRB/00001','Receipt','')"))
    _bind(db, {"daybook": {"slno", "tdate", "accode", "opaccode", "amount", "control"},
               "daybookpart": {"slno", "vchno", "particular", "chequeno"},
               "pdclist": {"slno", "control"},
               "delpart": {"slno", "tdate", "part", "control", "utype", "ttype", "updtdate", "updttime", "uid", "ic"}})
    return db


def test_payment_pending_only_vp():
    rows = PaymentConfirmationService(make_pay_db()).pending()
    assert len(rows) == 1
    assert rows[0]["vchno"] == "VPB/00001"
    assert rows[0]["amount"] == Decimal("5000.00")  # abs of negative


def test_payment_confirm_promotes_control():
    db = make_pay_db()
    svc = PaymentConfirmationService(db)
    svc.confirm(10, "VPB/00001")
    assert int(db.scalar("SELECT MIN(control) FROM daybook WHERE slno=10")) == LIVE_CONTROL
    assert int(db.scalar("SELECT MAX(control) FROM daybook WHERE slno=10")) == LIVE_CONTROL
    assert int(db.scalar("SELECT control FROM pdclist WHERE slno=10")) == LIVE_CONTROL
    assert int(db.scalar("SELECT COUNT(*) FROM delpart WHERE slno=10")) == 1


def test_payment_permission_gate():
    db = make_pay_db()
    blocked = AppSession(user_code="u1", user_name="U1", selected_database="demo",
                         blocked_items={"ALLOWPMNTCONFIRMATION"})
    svc = PaymentConfirmationService(db, blocked)
    with pytest.raises(PaymentConfirmationError):
        svc.confirm(10, "VPB/00001")
