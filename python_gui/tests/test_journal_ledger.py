"""Journal posting (balanced multi-line) + Account Ledger / Day Book reads."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine, zero_sum
from python_gui.modules.account_ledger.service import AccountLedgerService
from python_gui.modules.day_book.service import DayBookService
from python_gui.modules.journal.service import JournalError, JournalService

sqlite3.register_adapter(Decimal, str)
_DAYBOOK_COLS = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode", "note", "narration"}
_DP_COLS = {"slno", "vchno", "particular", "staff", "tdate", "ic", "uid", "control"}


def make_engine():
    db = Database()
    db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT, note TEXT, narration TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, staff TEXT, tdate TEXT, ic TEXT, uid TEXT, control INT)"))
        c.execute(text("CREATE TABLE accountm (accode TEXT PRIMARY KEY, name TEXT, actype2 TEXT, opbal NUM, opbalb NUM)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        for a, n, ob in [("CASH", "Cash", 1000), ("C0001", "Customer 1", 0), ("RENT", "Rent", 0)]:
            c.execute(text("INSERT INTO accountm VALUES (:a,:n,' ',:o,:o)"), {"a": a, "n": n, "o": ob})
    pe = PostingEngine(db)
    pe.db.table_exists = lambda t: t in ("daybook", "daybookpart", "accountm", "generali")
    pe.db.column_exists = lambda t, c: (c in _DAYBOOK_COLS) if t == "daybook" else (c in _DP_COLS) if t == "daybookpart" else True
    pe.db.columns = lambda t: _DAYBOOK_COLS if t == "daybook" else _DP_COLS if t == "daybookpart" else set()
    return db, pe


def test_journal_balanced_posts_zero_sum():
    db, pe = make_engine()
    svc = JournalService(pe)
    res = svc.save([
        {"particulars": "RENT", "amountd": "5000", "amountc": "0", "rownote": "rent"},
        {"particulars": "CASH", "amountd": "0", "amountc": "5000", "rownote": "paid"},
    ], "2026-06-17", "June rent", "A")
    rows = db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno = :s", {"s": res["slno"]})
    by = {r["accode"]: Decimal(str(r["amount"])) for r in rows}
    assert by["RENT"] == Decimal("-5000.00")   # debit negative
    assert by["CASH"] == Decimal("5000.00")    # credit positive
    assert zero_sum(rows) == Decimal("0.00")
    assert res["vchno"] == "JLB/00001"
    # opposite accounts: RENT(debit) opp=first credit=CASH; CASH(credit) opp=first debit=RENT
    opp = {r["accode"]: r["opaccode"] for r in rows}
    assert opp["RENT"] == "CASH" and opp["CASH"] == "RENT"


def test_journal_unbalanced_rejected():
    _, pe = make_engine()
    with pytest.raises(JournalError, match="not equal"):
        JournalService(pe).save([
            {"particulars": "RENT", "amountd": "5000", "amountc": "0"},
            {"particulars": "CASH", "amountd": "0", "amountc": "4000"},
        ], "2026-06-17", "", "A")


def test_journal_both_sides_in_row_rejected():
    _, pe = make_engine()
    with pytest.raises(JournalError, match="both"):
        JournalService(pe).save([{"particulars": "RENT", "amountd": "10", "amountc": "10"}],
                                "2026-06-17", "", "A")


def test_journal_invalid_account_rejected():
    _, pe = make_engine()
    with pytest.raises(JournalError, match="Invalid account"):
        JournalService(pe).save([
            {"particulars": "GHOST", "amountd": "10", "amountc": "0"},
            {"particulars": "CASH", "amountd": "0", "amountc": "10"},
        ], "2026-06-17", "", "A")


def test_ledger_opening_and_running_balance():
    db, pe = make_engine()
    # CASH opening 1000 (debit-style positive opbal in master, stored as-is)
    JournalService(pe).save([
        {"particulars": "RENT", "amountd": "200", "amountc": "0"},
        {"particulars": "CASH", "amountd": "0", "amountc": "200"},
    ], "2026-06-10", "", "A")
    led = AccountLedgerService(db).ledger("CASH", "2026-06-01", "2026-06-30")
    assert len(led["rows"]) == 1
    # opening = opbal(1000) + prior(0); after +200 credit running = 1200
    assert led["rows"][0]["credit"] == Decimal("200.00")
    assert led["closing"] == Decimal("1200.00")


def test_daybook_cash_balance_and_entries():
    db, pe = make_engine()
    JournalService(pe).save([
        {"particulars": "RENT", "amountd": "200", "amountc": "0"},
        {"particulars": "CASH", "amountd": "0", "amountc": "200"},
    ], "2026-06-17", "", "A")
    svc = DayBookService(db)
    bal = svc.cash_balances("2026-06-17", "2026-06-17")
    # base 1000, nothing before from-date -> opening 1000; closing includes +200 -> 1200
    assert bal["opbal"] == Decimal("1000.00") and bal["clbal"] == Decimal("1200.00")
    entries = svc.entries("2026-06-17", "2026-06-17")
    assert len(entries) == 2
