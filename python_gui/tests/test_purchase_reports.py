"""Purchase reports (net/monthly/supplier/checklist) + bill confirmation."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.purchase_confirmation.service import (
    LIVE_CONTROL,
    PurchaseConfirmationService,
)
from python_gui.modules.purchase_reports.service import PurchaseReportsService

sqlite3.register_adapter(Decimal, str)

_COLS = {"slno", "billno", "docno", "tdate", "suppcode", "name", "billamt", "pamt",
         "addamt", "eamt", "discount", "taxamt", "sgst", "cgst", "igst", "hmc",
         "round", "netamt", "control", "pr"}


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text(
            "CREATE TABLE purchasem (slno INT, billno TEXT, docno TEXT, tdate TEXT, suppcode TEXT, name TEXT, "
            "billamt NUM, pamt NUM, addamt NUM, eamt NUM, discount NUM, taxamt NUM, sgst NUM, cgst NUM, "
            "igst NUM, hmc NUM, round NUM, netamt NUM, control INT, pr TEXT)"))
        # live bills (control 1) in June + July
        c.execute(text("INSERT INTO purchasem VALUES (1,'B1','D1','2026-06-10','S1','ACME',10000,0,0,0,0,300,150,150,0,0,0,10300,1,'P')"))
        c.execute(text("INSERT INTO purchasem VALUES (2,'','D2','2026-06-15','S1','ACME',5000,1000,0,0,0,150,75,75,0,0,0,5150,1,'P')"))
        c.execute(text("INSERT INTO purchasem VALUES (3,'B3','D3','2026-07-01','S2','BETA',2000,0,0,0,0,60,30,30,0,0,0,2060,1,'P')"))
        # provisional bills (control 4, pr 'P') awaiting confirmation
        c.execute(text("INSERT INTO purchasem VALUES (4,'B4','D4','2026-06-20','S2','BETA',7000,2000,0,0,0,0,0,0,0,0,0,7000,4,'P')"))
        c.execute(text("INSERT INTO purchasem VALUES (5,'B5','D5','2026-06-21','S1','ACME',3000,0,0,0,0,0,0,0,0,0,0,3000,4,'P')"))
    db.table_exists = lambda t: t == "purchasem"
    db.column_exists = lambda t, col: t == "purchasem" and col in _COLS
    db.columns = lambda t: _COLS if t == "purchasem" else set()
    return db


def test_net_purchase_totals():
    # live bills only (control <= 1) -> slno 1,2,3
    res = PurchaseReportsService(make_db()).purchase_book("2026-06-01", "2026-06-30")
    assert res["count"] == 2
    assert res["totals"]["billamt"] == Decimal("15000.00")
    assert res["totals"]["netamt"] == Decimal("15450.00")


def test_monthly_purchase_grouping():
    rows = PurchaseReportsService(make_db()).monthly_purchase("2026-01-01", "2026-12-31")
    months = {r["month"]: r for r in rows}
    assert months["2026-06"]["count"] == 2 and months["2026-07"]["count"] == 1
    assert months["2026-06"]["billamt"] == Decimal("15000.00")


def test_supplier_wise():
    rows = PurchaseReportsService(make_db()).supplier_wise("2026-01-01", "2026-12-31")
    by = {r["suppcode"]: r for r in rows}
    assert by["S1"]["count"] == 2 and by["S2"]["count"] == 1
    assert by["S1"]["name"] == "ACME"


def test_check_list_billno_fallback():
    rows = PurchaseReportsService(make_db()).check_list("2026-06-01", "2026-06-30")
    bills = {r["slno"]: r["billno"] for r in rows}
    assert bills[1] == "B1"
    assert bills[2] == "D2"  # blank billno falls back to docno


def test_confirmation_pending_and_confirm():
    db = make_db()
    svc = PurchaseConfirmationService(db)
    pending = svc.pending("2026-01-01", "2026-12-31")
    # provisional bills: slno 4, 5 (control=4, pr='P')
    assert {p["slno"] for p in pending} == {4, 5}
    assert {float(p["balance"]) for p in pending} == {5000.0, 3000.0}
    svc.confirm(4)
    assert int(db.scalar("SELECT control FROM purchasem WHERE slno=4")) == LIVE_CONTROL
    assert {p["slno"] for p in svc.pending("2026-01-01", "2026-12-31")} == {5}
