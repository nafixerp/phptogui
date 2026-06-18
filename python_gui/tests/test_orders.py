"""Order Bill — advance posting balance + orderm header save."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine, zero_sum
from python_gui.modules.orders.service import OrderService

sqlite3.register_adapter(Decimal, str)
_DB_COLS = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode"}
_DP_COLS = {"slno", "tdate", "control", "particular", "vchno", "rate"}
_ORDERM = {"slno", "ordno", "tdate", "custcode", "custname", "rate", "billamt",
           "advance", "refund", "status", "control", "closed", "cbcode", "note"}


def make():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, tdate TEXT, control INT, particular TEXT, vchno TEXT, rate NUM)"))
        cols = ", ".join(f"{x} TEXT" for x in sorted(_ORDERM - {"slno", "ordno"}))
        c.execute(text(f"CREATE TABLE orderm (slno INT, ordno INT, {cols})"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
    pe = PostingEngine(db)
    pe.db.table_exists = lambda t: t in ("daybook", "daybookpart", "orderm", "generali")
    pe.db.column_exists = lambda t, c: True
    pe.db.columns = lambda t: _DB_COLS if t == "daybook" else _DP_COLS if t == "daybookpart" else _ORDERM if t == "orderm" else set()
    return db, OrderService(pe)


def lines(db, slno):
    return db.fetchall("SELECT accode, amount, opaccode FROM daybook WHERE slno = :s ORDER BY sno", {"s": slno})


def test_order_advance_cash_balances():
    db, svc = make()
    res = svc.save({"custcode": "C0001", "custname": "ACME", "tdate": "2026-06-17",
                    "billamt": "20000", "advance": "5000", "cbcode": "CASH"})
    rows = lines(db, res["slno"])
    by = {r["accode"]: Decimal(str(r["amount"])) for r in rows}
    assert by["CASH"] == Decimal("-5000.00")     # cash received (debit-side negative)
    assert by["C0001"] == Decimal("5000.00")     # customer advance credited
    assert zero_sum(rows) == Decimal("0.00")
    # orderm header persisted with reserved ordno
    m = db.fetchone("SELECT ordno, custcode, advance FROM orderm WHERE slno = :s", {"s": res["slno"]})
    assert m["custcode"] == "C0001" and int(m["ordno"]) == res["ordno"]


def test_order_advance_split_cash_card_cheque():
    db, svc = make()
    res = svc.save({"custcode": "C0001", "tdate": "2026-06-17", "advance": "5000",
                    "cbcode": "HDFC", "ccamt": "2000", "chqamt": "1000", "chq_bank": "HDFC"})
    rows = lines(db, res["slno"])
    by_total = sum((Decimal(str(r["amount"])) for r in rows), Decimal("0"))
    assert by_total == Decimal("0.00")           # cash(2000)+card(2000)+chq(1000) == advance(5000)
    accs = [r["accode"] for r in rows]
    assert "C0001" in accs


def test_order_no_advance_no_daybook():
    db, svc = make()
    res = svc.save({"custcode": "C0001", "tdate": "2026-06-17", "billamt": "20000", "advance": "0"})
    assert res["advance_lines"] == 0
    assert lines(db, res["slno"]) == []
    # but orderm row still created
    assert db.fetchone("SELECT 1 FROM orderm WHERE slno = :s", {"s": res["slno"]}) is not None
