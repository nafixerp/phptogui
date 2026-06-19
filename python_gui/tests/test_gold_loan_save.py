"""Bucket B: gold loan save — loan/loan_items create + repayment collection."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.gold_loan.service import GoldLoanSaveError, GoldLoanSaveService

sqlite3.register_adapter(Decimal, str)

# a "newer app" loan schema (the one the controller writes)
_LOAN = {"slno", "ccode", "cname", "tdate", "loanamt", "intrate", "duedate", "remarks",
         "status", "control", "paidamt", "balance", "closed"}
_LI = {"slno", "icode", "idesc", "purity", "grosswgt", "netwgt", "finewgt", "grate", "value"}
_LC = {"slno", "tdate", "principal", "interest", "total", "amount", "control"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE loan (slno INT, ccode TEXT, cname TEXT, tdate TEXT, loanamt NUM, intrate NUM, "
                       "duedate TEXT, remarks TEXT, status TEXT, control INT, paidamt NUM, balance NUM, closed TEXT)"))
        c.execute(text("CREATE TABLE loan_items (slno INT, icode TEXT, idesc TEXT, purity NUM, grosswgt NUM, netwgt NUM, finewgt NUM, grate NUM, value NUM)"))
        c.execute(text("CREATE TABLE loancolln (slno INT, tdate TEXT, principal NUM, interest NUM, total NUM, amount NUM, control INT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    cmap = {"loan": _LOAN, "loan_items": _LI, "loancolln": _LC, "generali": {"code", "cvalue"}}
    tabs = set(cmap)
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: c in cmap.get(t, set())
    pe.db.columns = lambda t: cmap.get(t, set())
    return db, pe


def test_create_loan_with_items():
    db, pe = make_engine()
    res = GoldLoanSaveService(pe, control=1).save(
        {"ccode": "C1", "cname": "ACME", "tdate": "2026-06-01", "loan_amount": 50000, "interest_rate": 18},
        [{"icode": "OG", "idesc": "Bangle", "grosswgt": 25.0, "netwgt": 24.0, "value": 50000}])
    assert res["slno"] > 0
    loan = db.fetchone("SELECT ccode, loanamt, intrate, status FROM loan WHERE slno=:s", {"s": res["slno"]})
    assert loan["ccode"] == "C1"
    assert Decimal(str(loan["loanamt"])) == Decimal("50000.00")
    assert Decimal(str(loan["intrate"])) == Decimal("18.00")
    assert loan["status"] == "open"
    assert int(db.scalar("SELECT COUNT(*) FROM loan_items WHERE slno=:s", {"s": res["slno"]})) == 1


def test_collection_updates_balance_and_closes():
    db, pe = make_engine()
    svc = GoldLoanSaveService(pe, control=1)
    r = svc.save({"ccode": "C1", "loan_amount": 10000}, [])
    # partial repayment 4000 -> balance 6000, still open
    svc.add_collection(r["slno"], principal=4000, interest=200, tdate="2026-06-20")
    loan = db.fetchone("SELECT paidamt, balance, status FROM loan WHERE slno=:s", {"s": r["slno"]})
    assert Decimal(str(loan["paidamt"])) == Decimal("4000.00")
    assert Decimal(str(loan["balance"])) == Decimal("6000.00")
    assert loan["status"] == "open"
    # final repayment 6000 -> balance 0, closed
    svc.add_collection(r["slno"], principal=6000, interest=100, tdate="2026-07-20")
    loan = db.fetchone("SELECT balance, status, closed FROM loan WHERE slno=:s", {"s": r["slno"]})
    assert Decimal(str(loan["balance"])) == Decimal("0.00")
    assert loan["status"] == "closed" and loan["closed"] == "Y"
    assert int(db.scalar("SELECT COUNT(*) FROM loancolln WHERE slno=:s", {"s": r["slno"]})) == 2


def test_update_existing_loan_replaces_items():
    db, pe = make_engine()
    svc = GoldLoanSaveService(pe, control=1)
    r = svc.save({"ccode": "C1", "loan_amount": 10000}, [{"icode": "OG", "value": 10000}])
    svc.save({"slno": r["slno"], "ccode": "C1", "loan_amount": 12000},
             [{"icode": "OS", "value": 12000}])
    assert Decimal(str(db.scalar("SELECT loanamt FROM loan WHERE slno=:s", {"s": r["slno"]}))) == Decimal("12000.00")
    items = db.fetchall("SELECT icode FROM loan_items WHERE slno=:s", {"s": r["slno"]})
    assert len(items) == 1 and items[0]["icode"] == "OS"


def test_validations():
    db, pe = make_engine()
    svc = GoldLoanSaveService(pe)
    with pytest.raises(GoldLoanSaveError):
        svc.save({"ccode": "", "loan_amount": 5000})
    with pytest.raises(GoldLoanSaveError):
        svc.save({"ccode": "C1", "loan_amount": 0})
    with pytest.raises(GoldLoanSaveError):
        svc.add_collection(0, 100, 0)
