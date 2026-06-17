"""Posting engine + Receipt/Payment tests — the double-entry zero-sum invariant.

Runs against a real in-memory SQLite engine with daybook/daybookpart/accountm/
generali/generals, asserting every posted transaction sums to zero and that
serial/voucher numbers advance correctly.
"""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine, zero_sum
from python_gui.modules.payment.service import PaymentError, PaymentService
from python_gui.modules.receipt.service import ReceiptError, ReceiptService

sqlite3.register_adapter(Decimal, str)

_DAYBOOK_COLS = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode", "note"}
_DP_COLS = {"slno", "vchno", "particular", "staff", "chequedate", "chequeno", "ic",
            "duedate", "uid", "refno", "slno2", "ttime", "rate", "taxperc", "taxamt",
            "interstate", "taxreverse", "ttype", "discount", "tdate", "control"}


def make_engine():
    db = Database()
    db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT, note TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, staff TEXT, chequedate TEXT, chequeno TEXT, ic TEXT, duedate TEXT, uid TEXT, refno TEXT, slno2 NUM, ttime TEXT, rate NUM, taxperc NUM, taxamt NUM, interstate TEXT, taxreverse TEXT, ttype TEXT, discount NUM, tdate TEXT, control INT)"))
        c.execute(text("CREATE TABLE accountm (accode TEXT PRIMARY KEY, actype2 TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE generals (code TEXT PRIMARY KEY, cvalue TEXT)"))
        for acc, t2 in [("CASH", "H"), ("HDFC", "B"), ("C0001", "C"), ("EXP01", " ")]:
            c.execute(text("INSERT INTO accountm VALUES (:a, :t)"), {"a": acc, "t": t2})
    pe = PostingEngine(db)
    # stub MySQL catalog probes
    pe.db.table_exists = lambda t: t in ("daybook", "daybookpart", "accountm", "generali", "generals")
    pe.db.column_exists = lambda t, c: (c in _DAYBOOK_COLS) if t == "daybook" else (c in _DP_COLS) if t == "daybookpart" else True
    pe.db.columns = lambda t: _DAYBOOK_COLS if t == "daybook" else _DP_COLS if t == "daybookpart" else set()
    return db, pe


def daybook_rows(db, slno):
    return db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno = :s ORDER BY rowid", {"s": slno})


# -- Receipt -----------------------------------------------------------------

def test_receipt_balances_to_zero_with_discount():
    db, pe = make_engine()
    svc = ReceiptService(pe)
    res = svc.save({"tdate": "2026-06-17", "cbcode": "CASH", "accode": "C0001",
                    "amount": "1000", "discount": "50"}, "A")
    rows = daybook_rows(db, res["slno"])
    assert len(rows) == 3
    # party +(amount+discount), cash -(amount), discount -(discount)
    by_acc = {r["accode"]: Decimal(str(r["amount"])) for r in rows}
    assert by_acc["C0001"] == Decimal("1050.00")
    assert by_acc["CASH"] == Decimal("-1000.00")
    assert by_acc["DISC"] == Decimal("-50.00")
    assert zero_sum(rows) == Decimal("0.00")
    assert res["vchno"] == "VRB/00001"


def test_receipt_no_discount_two_lines():
    db, pe = make_engine()
    res = ReceiptService(pe).save({"tdate": "2026-06-17", "cbcode": "HDFC",
                                   "accode": "C0001", "amount": "500"}, "A")
    rows = daybook_rows(db, res["slno"])
    assert len(rows) == 2 and zero_sum(rows) == Decimal("0.00")


def test_receipt_validation():
    _, pe = make_engine()
    svc = ReceiptService(pe)
    with pytest.raises(ReceiptError, match="date is required"):
        svc.save({"cbcode": "CASH", "accode": "C0001", "amount": "10"}, "A")
    with pytest.raises(ReceiptError, match="greater than zero"):
        svc.save({"tdate": "2026-06-17", "cbcode": "CASH", "accode": "C0001", "amount": "0"}, "A")
    with pytest.raises(ReceiptError, match="not found"):
        svc.save({"tdate": "2026-06-17", "cbcode": "NOPE", "accode": "C0001", "amount": "10"}, "A")


def test_serial_and_voucher_increment():
    db, pe = make_engine()
    svc = ReceiptService(pe)
    r1 = svc.save({"tdate": "2026-06-17", "cbcode": "CASH", "accode": "C0001", "amount": "100"}, "A")
    r2 = svc.save({"tdate": "2026-06-17", "cbcode": "CASH", "accode": "C0001", "amount": "200"}, "A")
    assert r2["slno"] == r1["slno"] + 1
    assert r1["vchno"] == "VRB/00001" and r2["vchno"] == "VRB/00002"


def test_receipt_edit_reuses_slno_and_replaces_lines():
    db, pe = make_engine()
    svc = ReceiptService(pe)
    r = svc.save({"tdate": "2026-06-17", "cbcode": "CASH", "accode": "C0001", "amount": "100"}, "A")
    svc.save({"tdate": "2026-06-17", "cbcode": "CASH", "accode": "C0001", "amount": "300",
              "slno": r["slno"], "vchno": r["vchno"]}, "E")
    rows = daybook_rows(db, r["slno"])
    assert len(rows) == 2  # old lines deleted, not duplicated
    assert {Decimal(str(x["amount"])) for x in rows} == {Decimal("300.00"), Decimal("-300.00")}


def test_receipt_delete_removes_lines():
    db, pe = make_engine()
    svc = ReceiptService(pe)
    r = svc.save({"tdate": "2026-06-17", "cbcode": "CASH", "accode": "C0001", "amount": "100"}, "A")
    svc.delete(r["slno"])
    assert daybook_rows(db, r["slno"]) == []


# -- Payment -----------------------------------------------------------------

def test_payment_balances_and_signs():
    db, pe = make_engine()
    res = PaymentService(pe).save({"tdate": "2026-06-17", "cbcode": "CASH",
                                   "accode": "EXP01", "amount": "750"}, "A")
    rows = daybook_rows(db, res["slno"])
    by_acc = {r["accode"]: Decimal(str(r["amount"])) for r in rows}
    assert by_acc["CASH"] == Decimal("750.00")     # cash/bank debit-side positive
    assert by_acc["EXP01"] == Decimal("-750.00")   # party negative
    assert zero_sum(rows) == Decimal("0.00")
    assert res["vchno"] == "VPB/00001"


def test_payment_separate_bank_voucher_prefix():
    db, pe = make_engine()
    # enable cash/bank-separate numbering; bank account -> VPB/, cash -> VPC/
    db.execute("INSERT INTO generals (code, cvalue) VALUES ('BankCashSeperateVoucherNo','Y')")
    svc = PaymentService(pe)
    bank = svc.save({"tdate": "2026-06-17", "cbcode": "HDFC", "accode": "EXP01", "amount": "10"}, "A")
    cash = svc.save({"tdate": "2026-06-17", "cbcode": "CASH", "accode": "EXP01", "amount": "10"}, "A")
    assert bank["vchno"].startswith("VPB/")
    assert cash["vchno"].startswith("VPC/")
