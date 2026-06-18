"""Register reads (column-guarded, totals) + PDF bill builder."""

from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.registers.service import RegisterService


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE salesm (slno INT, billno TEXT, tdate TEXT, custname TEXT, billamt NUM, netamt NUM, discount NUM, control INT)"))
        c.execute(text("INSERT INTO salesm VALUES (1,'S001','2026-06-10','ACME',10000,10500,100,1)"))
        c.execute(text("INSERT INTO salesm VALUES (2,'S002','2026-06-11','BETA',5000,5300,0,1)"))
        c.execute(text("INSERT INTO salesm VALUES (3,'S003','2026-07-01','GAMMA',9999,9999,0,1)"))  # out of range
    db.table_exists = lambda t: t == "salesm"
    db.columns = lambda t: {"slno", "billno", "tdate", "custname", "billamt", "netamt", "discount", "control"}
    return db


def test_sales_register_range_and_totals():
    svc = RegisterService(make_db())
    res = svc.register("salesm", "custname", "2026-06-01", "2026-06-30")
    assert len(res["rows"]) == 2                       # July bill excluded
    assert res["totals"]["billamt"] == Decimal("15000.00")
    assert res["totals"]["netamt"] == Decimal("15800.00")
    assert {r["party"] for r in res["rows"]} == {"ACME", "BETA"}


def test_register_missing_table_empty():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    db.table_exists = lambda t: False
    assert RegisterService(db).register("salesm", "custname", "2026-01-01", "2026-12-31")["rows"] == []


def test_register_control_filter():
    db = make_db()
    res = RegisterService(db, rlevel=1).register("salesm", "custname", "2026-06-01", "2026-06-30")
    # all rows control=1 <= rlevel 1 -> included
    assert len(res["rows"]) == 2


def test_pdf_build_or_skip(tmp_path):
    import importlib
    pdf = importlib.import_module("python_gui.core.pdf")
    if getattr(pdf, "_RL_ERROR", "x") is not None:
        # reportlab not installed in this environment -> the guard must raise clearly
        try:
            pdf.build_document(str(tmp_path / "x.pdf"), title="T", shop={"name": "S"}, details=[])
            assert False, "expected RuntimeError without reportlab"
        except RuntimeError as e:
            assert "reportlab" in str(e)
        return
    path = pdf.build_document(str(tmp_path / "bill.pdf"), title="TAX INVOICE",
                              shop={"name": "GoldShop", "phone": "123"},
                              details=[("Bill No", "S001"), ("Customer", "ACME")],
                              items=[{"item": "Ring", "amt": "50500"}],
                              item_columns=[("item", "Item"), ("amt", "Amount")])
    assert (tmp_path / "bill.pdf").exists() and pdf.format_money(50500) == "₹50,500.00"
