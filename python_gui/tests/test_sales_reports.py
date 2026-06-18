"""Sales reports (net/monthly/salesman/checklist) + bill confirmation."""

from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.sales_confirmation.service import (
    CONFIRMED_STATUS,
    SalesConfirmationService,
)
from python_gui.modules.sales_reports.service import SalesReportsService

_COLS = {"slno", "billno", "tdate", "custcode", "custname", "billamt", "eamt",
         "staxamt", "discount", "sretamt", "netamt", "smcode", "control", "status"}


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE salesm (slno INT, billno TEXT, tdate TEXT, custcode TEXT, custname TEXT, "
                       "billamt NUM, eamt NUM, staxamt NUM, discount NUM, sretamt NUM, netamt NUM, smcode TEXT, control INT, status INT)"))
        c.execute(text("INSERT INTO salesm VALUES (1,'S1','2026-06-10','C1','ACME',10000,0,300,0,0,10300,'SM1',1,1)"))
        c.execute(text("INSERT INTO salesm VALUES (2,'S2','2026-06-15','C2','BETA',5000,0,150,0,0,5150,'SM1',1,2)"))
        c.execute(text("INSERT INTO salesm VALUES (3,'S3','2026-07-01','C3','GAMMA',2000,0,60,0,0,2060,'SM2',1,1)"))
    db.table_exists = lambda t: t == "salesm"
    db.columns = lambda t: _COLS if t == "salesm" else set()
    return db


def test_net_sales_totals():
    res = SalesReportsService(make_db()).net_sales("2026-06-01", "2026-06-30")
    assert res["count"] == 2
    assert res["totals"]["billamt"] == Decimal("15000.00")
    assert res["totals"]["netamt"] == Decimal("15450.00")


def test_monthly_sales_grouping():
    rows = SalesReportsService(make_db()).monthly_sales("2026-01-01", "2026-12-31")
    months = {r["month"]: r for r in rows}
    assert months["2026-06"]["count"] == 2 and months["2026-07"]["count"] == 1
    assert months["2026-06"]["billamt"] == Decimal("15000.00")


def test_salesman_wise():
    rows = SalesReportsService(make_db()).salesman_wise("2026-01-01", "2026-12-31")
    by = {r["smcode"]: r for r in rows}
    assert by["SM1"]["count"] == 2 and by["SM2"]["count"] == 1


def test_check_list():
    rows = SalesReportsService(make_db()).check_list("2026-06-01", "2026-06-30")
    assert len(rows) == 2 and {str(r["billno"]) for r in rows} == {"S1", "S2"}


def test_confirmation_pending_and_confirm():
    db = make_db()
    svc = SalesConfirmationService(db)
    pending = svc.pending("2026-01-01", "2026-12-31")
    # bills with status != confirmed(2): S1 (1), S3 (1)
    assert {p["slno"] for p in pending} == {1, 3}
    svc.confirm(1, True)
    assert int(db.scalar("SELECT status FROM salesm WHERE slno=1")) == CONFIRMED_STATUS
    assert {p["slno"] for p in svc.pending("2026-01-01", "2026-12-31")} == {3}
