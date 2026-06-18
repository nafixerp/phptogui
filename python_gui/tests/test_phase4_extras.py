"""Debit/Credit Note + Expense Voucher postings (zero-sum) + Day Summary."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine, zero_sum
from python_gui.modules.day_summary.service import DaySummaryService
from python_gui.modules.debit_credit_note.service import DebitCreditNoteService
from python_gui.modules.expense_voucher.service import ExpenseVoucherService

sqlite3.register_adapter(Decimal, str)
_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP = {"slno", "vchno", "particular", "tdate", "control"}


def make_pe():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, tdate TEXT, control INT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    pe.db.table_exists = lambda t: t in ("daybook", "daybookpart", "generali")
    pe.db.column_exists = lambda t, c: True
    pe.db.columns = lambda t: _DB if t == "daybook" else _DP if t == "daybookpart" else set()
    return db, pe


def rows(db, slno):
    return db.fetchall("SELECT accode, amount FROM daybook WHERE slno = :s ORDER BY sno", {"s": slno})


def test_debit_note_balances():
    db, pe = make_pe()
    res = DebitCreditNoteService(pe).save("D", "SUPP1", "RATEDIFF", "1000", "1180", "180")
    r = rows(db, res["slno"])
    by = {x["accode"]: Decimal(str(x["amount"])) for x in r}
    assert by["SUPP1"] == Decimal("-1180.00")
    assert by["RATEDIFF"] == Decimal("1000.00")
    assert by["SGST"] == Decimal("90.00") and by["CGST"] == Decimal("90.00")
    assert zero_sum(r) == Decimal("0.00")
    assert res["vchno"] == "DN/00001"


def test_credit_note_signs_reversed():
    db, pe = make_pe()
    res = DebitCreditNoteService(pe).save("C", "CUST1", "RATEDIFF", "1000", "1180", "180")
    by = {x["accode"]: Decimal(str(x["amount"])) for x in rows(db, res["slno"])}
    assert by["CUST1"] == Decimal("1180.00") and by["SGST"] == Decimal("-90.00")
    assert zero_sum(rows(db, res["slno"])) == Decimal("0.00")
    assert res["vchno"] == "CN/00001"


def test_expense_voucher_balances():
    db, pe = make_pe()
    res = ExpenseVoucherService(pe).save({"pamtAc": "RENT", "bamt": "10000", "taxamt": "0",
                                          "discount": "0", "paidamt": "10000", "cbAc": "CASH",
                                          "netamt": "10000"})
    r = rows(db, res["slno"])
    by = {x["accode"]: Decimal(str(x["amount"])) for x in r}
    assert by["RENT"] == Decimal("-10000.00") and by["CASH"] == Decimal("10000.00")
    assert zero_sum(r) == Decimal("0.00")


def test_expense_voucher_with_party_and_tax():
    db, pe = make_pe()
    res = ExpenseVoucherService(pe).save({"pamtAc": "RENT", "bamt": "10000", "taxamt": "1800",
                                          "discount": "0", "paidamt": "5000", "partyCode": "SUPP1",
                                          "netamt": "11800", "cbAc": "CASH"})
    assert zero_sum(rows(db, res["slno"])) == Decimal("0.00")


def test_day_summary_groups_by_date():
    db, pe = make_pe()
    DebitCreditNoteService(pe).save("D", "SUPP1", "RATEDIFF", "1000", "1000", "0", tdate="2026-06-10")
    DebitCreditNoteService(pe).save("C", "CUST1", "RATEDIFF", "500", "500", "0", tdate="2026-06-11")
    res = DaySummaryService(db).summary("2026-06-01", "2026-06-30")
    assert len(res["rows"]) == 2
    # totals: each balanced voucher contributes equal debit and credit
    assert res["total_debit"] == res["total_credit"]
