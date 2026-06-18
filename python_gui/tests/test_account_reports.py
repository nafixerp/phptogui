"""Bucket A accounts: chart of accounts, group summary, cash balance."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.account_reports.service import AccountReportsService

sqlite3.register_adapter(Decimal, str)


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE accountm (accode TEXT, name TEXT, grcode TEXT, actype1 TEXT, opbal NUM, opbalb NUM)"))
        c.execute(text("CREATE TABLE accountg (grcode TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE daybook (accode TEXT, tdate TEXT, amount NUM, control INT)"))
        # CASH asset: opening 1000, +500 receipt, -200 payment within period
        c.execute(text("INSERT INTO accountm VALUES ('CASH','Cash','CA','A',1000,1000)"))
        c.execute(text("INSERT INTO accountm VALUES ('SALES','Sales A/c','IN','R',0,0)"))
        c.execute(text("INSERT INTO accountg VALUES ('CA','Cash & Bank')"))
        c.execute(text("INSERT INTO accountg VALUES ('IN','Income')"))
        c.execute(text("INSERT INTO daybook VALUES ('CASH','2026-06-10',500,1)"))
        c.execute(text("INSERT INTO daybook VALUES ('CASH','2026-06-12',-200,1)"))
        c.execute(text("INSERT INTO daybook VALUES ('SALES','2026-06-10',5000,1)"))
        c.execute(text("INSERT INTO daybook VALUES ('CASH','2026-07-01',999,1)"))  # after as-of -> excluded
    db.table_exists = lambda t: t in {"accountm", "accountg", "daybook"}
    db.column_exists = lambda t, col: True
    db.columns = lambda t: set()
    return db


def test_cash_balance_as_of():
    svc = AccountReportsService(make_db())
    # 1000 + 500 - 200 = 1300 (July entry excluded)
    assert svc.cash_balance("2026-06-30") == Decimal("1300.00")
    # without as-of includes the July entry -> 2299
    assert svc.cash_balance() == Decimal("2299.00")


def test_chart_of_accounts_balances():
    rows = AccountReportsService(make_db()).chart_of_accounts("2026-06-30")
    by = {r["accode"]: r for r in rows}
    assert by["CASH"]["balance"] == Decimal("1300.00")
    assert by["CASH"]["credit"] == Decimal("1300.00") and by["CASH"]["debit"] == Decimal("0.00")
    assert by["SALES"]["balance"] == Decimal("5000.00")
    assert by["CASH"]["group_name"] == "Cash & Bank"


def test_chart_type_filter_and_group_summary():
    svc = AccountReportsService(make_db())
    assets = svc.chart_of_accounts("2026-06-30", type_="Assets Only")
    assert {r["accode"] for r in assets} == {"CASH"}
    groups = {g["group"]: g for g in svc.group_summary("2026-06-30")}
    assert groups["Cash & Bank"]["credit"] == Decimal("1300.00")
    assert groups["Income"]["credit"] == Decimal("5000.00")
