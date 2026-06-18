"""Staff transaction posting (zero-sum) + Order cancel (reverse advance)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine, zero_sum
from python_gui.modules.order_cancel.service import OrderCancelError, OrderCancelService
from python_gui.modules.staff_transaction.service import StaffError, StaffTransactionService

sqlite3.register_adapter(Decimal, str)
_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP = {"slno", "vchno", "particular", "tdate", "control", "uid"}


def make_pe():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, tdate TEXT, control INT, uid TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    pe.db.table_exists = lambda t: t in ("daybook", "daybookpart", "generali")
    pe.db.column_exists = lambda t, c: True
    pe.db.columns = lambda t: _DB if t == "daybook" else _DP if t == "daybookpart" else set()
    return db, pe


def rows(db, slno):
    return db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno = :s ORDER BY sno", {"s": slno})


def test_staff_transaction_balances():
    db, pe = make_pe()
    res = StaffTransactionService(pe).save(
        [{"code": "STF1", "amount": "1000"}, {"code": "STF2", "amount": "500"}],
        accode="CASH", is_debit=True)
    r = rows(db, res["slno"])
    by = {x["accode"]: Decimal(str(x["amount"])) for x in r}
    assert by["STF1"] == Decimal("-1000.00")     # debit (pay out) -> negative
    assert by["STF2"] == Decimal("-500.00")
    assert by["CASH"] == Decimal("1500.00")      # contra = +total
    assert zero_sum(r) == Decimal("0.00")
    assert res["vchno"] == "JLB/00001"


def test_staff_transaction_credit_side():
    db, pe = make_pe()
    res = StaffTransactionService(pe).save([{"code": "STF1", "amount": "200"}],
                                           accode="CASH", is_debit=False)
    by = {x["accode"]: Decimal(str(x["amount"])) for x in rows(db, res["slno"])}
    assert by["STF1"] == Decimal("200.00") and by["CASH"] == Decimal("-200.00")


def test_staff_requires_items():
    _, pe = make_pe()
    with pytest.raises(StaffError, match="No items"):
        StaffTransactionService(pe).save([], "CASH", True)


def test_order_cancel_reverses_advance():
    db, pe = make_pe()
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE orderm (slno INT, ordno INT, custname TEXT, tdate TEXT, status INT, closed TEXT)"))
        c.execute(text("INSERT INTO orderm VALUES (50, 7, 'ACME', '2026-06-17', 1, 'N')"))
        c.execute(text("INSERT INTO daybook VALUES (50,'2026-06-17','CASH',-5000,1,1,'C0001')"))
        c.execute(text("INSERT INTO daybook VALUES (50,'2026-06-17','C0001',5000,1,2,'CASH')"))
        c.execute(text("INSERT INTO daybookpart (slno, vchno) VALUES (50, '')"))
    db.table_exists = lambda t: t in ("orderm", "daybook", "daybookpart")
    db.column_exists = lambda t, c: True
    svc = OrderCancelService(db)
    res = svc.cancel(7)
    assert res["slno"] == 50
    assert db.fetchall("SELECT 1 FROM daybook WHERE slno = 50") == []   # advance reversed
    assert db.scalar("SELECT closed FROM orderm WHERE slno = 50") == "Y"
    assert int(db.scalar("SELECT status FROM orderm WHERE slno = 50")) == 9


def test_order_cancel_not_found():
    db, pe = make_pe()
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE orderm (slno INT, ordno INT, custname TEXT, tdate TEXT, status INT, closed TEXT)"))
    db.table_exists = lambda t: t == "orderm"
    with pytest.raises(OrderCancelError, match="not found"):
        OrderCancelService(db).cancel(999)
