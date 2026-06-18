"""Sales calc (line amount + calcTotals) and end-to-end calc->post zero-sum."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine, zero_sum
from python_gui.modules.sales import calc
from python_gui.modules.sales.service import SalesPostingService

sqlite3.register_adapter(Decimal, str)
_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode", "vtype"}
_DP = {"slno", "vchno", "particular", "tdate", "control"}


def make_pe():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT, vtype TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT, tdate TEXT, control INT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE generals (code TEXT PRIMARY KEY, cvalue TEXT)"))
    pe = PostingEngine(db)
    pe.db.table_exists = lambda t: t in ("daybook", "daybookpart", "generali", "generals")
    pe.db.column_exists = lambda t, c: True
    pe.db.columns = lambda t: _DB if t == "daybook" else _DP if t == "daybookpart" else set()
    return db, pe


def test_line_amount_weight_based():
    # 10g @ 5000 + 500 MC, no stone -> 50500
    assert calc.line_amount({"weight": "10", "rate": "5000", "making_charge": "500"}) == Decimal("50500.00")
    # stkinnos -> qty * rate
    assert calc.line_amount({"qty": "2", "rate": "100", "stkinnos": "Y"}) == Decimal("200.00")
    # net weight = weight - stone
    assert calc.line_amount({"weight": "10", "stone_wgt": "2", "rate": "1000", "stone_price": "300"}) == Decimal("8300.00")


def test_calctotals_exclusive_tax_and_discount():
    items = [{"weight": "10", "rate": "5000", "making_charge": "500"},
             {"weight": "10", "rate": "5000", "making_charge": "500"}]
    for it in items:
        it["amount"] = str(calc.line_amount(it))
    amt = calc.compute(items, extra={"tax_perc": "3", "discount": "1000",
                                      "customer_code": "C0001", "cashbank_code": "CASH"})
    assert amt["bill_total"] == Decimal("101000.00")
    assert amt["tax"] == Decimal("3030.00")
    assert amt["sgst"] == Decimal("1515.00") and amt["cgst"] == Decimal("1515.00")
    assert amt["net_total"] == Decimal("104030.00")      # bill + tax
    assert amt["discount"] == Decimal("1000.00")


def test_calctotals_inclusive_tax():
    # tax-internal item: amount includes tax; base = amount*100/(100+rate)
    items = [{"amount": "10300", "taxinternal": "Y"}]
    amt = calc.compute(items, extra={"tax_perc": "3"})
    # base = 10300*100/103 = 10000 ; tax = 300
    assert amt["bill_total"] == Decimal("10000.00")
    assert amt["tax"] == Decimal("300.00")


def test_calc_then_post_balances_to_zero():
    db, pe = make_pe()
    items = [{"weight": "10", "rate": "5000", "making_charge": "500"}]
    items[0]["amount"] = str(calc.line_amount(items[0]))
    amt = calc.compute(items, extra={"tax_perc": "3", "discount": "500",
                                     "customer_code": "C0001", "cashbank_code": "CASH"})
    res = SalesPostingService(pe).post(0, "2026-06-17", amt, items=items)
    rows = db.fetchall("SELECT accode, amount FROM daybook WHERE slno = :s", {"s": res["slno"]})
    assert zero_sum(rows) == Decimal("0.00")
    by = {r["accode"]: Decimal(str(r["amount"])) for r in rows}
    # RS = bill_total 50500 ; tax split 1515/... wait 3% of 50500 = 1515 total -> 757.5/757.5
    assert by["RS"] == Decimal("50500.00")
    assert by["DISC"] == Decimal("-500.00")
