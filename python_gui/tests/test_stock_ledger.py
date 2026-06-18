"""Phase 7 batch 2: stock movement engine, period ledger, barcode history, stock summary."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.stock import StockCalculator
from python_gui.modules.barcode_history.service import BarcodeHistoryService
from python_gui.modules.stock_period_ledger.service import StockPeriodLedgerService
from python_gui.modules.stock_summary.service import StockSummaryService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


def make_stock_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT, itype TEXT, opqty INT, opweight NUM, opstonewgt NUM, "
                       "opqtyb INT, opweightb NUM, opstonewgtb NUM, disabled INT, showinstkrep TEXT, grpcode TEXT, subgrpcode TEXT)"))
        c.execute(text("CREATE TABLE salesm (slno INT, tdate TEXT, billno TEXT, control INT, status INT)"))
        c.execute(text("CREATE TABLE salesd (slno INT, code TEXT, qty INT, weight NUM, stonewgt NUM, cost NUM, amount NUM, jcode TEXT, rate NUM, bcode INT)"))
        c.execute(text("CREATE TABLE purchasem (slno INT, tdate TEXT, control INT, status INT)"))
        c.execute(text("CREATE TABLE purchased (slno INT, code TEXT, qty INT, weight NUM, stwgt NUM, amount NUM)"))
        # item R1: opening 10 qty / 100g
        c.execute(text("INSERT INTO items VALUES ('R1','Ring','G',10,100.0,0,10,100.0,0,0,'Y','GG','SS')"))
        # opening period: a purchase BEFORE d1 adds 5/50
        c.execute(text("INSERT INTO purchasem VALUES (1,'2026-05-01',1,1)"))
        c.execute(text("INSERT INTO purchased VALUES (1,'R1',5,50.0,0,500000)"))
        # within period: sale of 2/20 (issued), purchase of 3/30 (received)
        c.execute(text("INSERT INTO salesm VALUES (2,'2026-06-10','S1',1,1)"))
        c.execute(text("INSERT INTO salesd VALUES (2,'R1',2,20.0,0,9000,200000,'',5000,0)"))
        c.execute(text("INSERT INTO purchasem VALUES (3,'2026-06-12',1,1)"))
        c.execute(text("INSERT INTO purchased VALUES (3,'R1',3,30.0,0,300000)"))
    _bind(db, {
        "items": {"code", "name", "itype", "opqty", "opweight", "opstonewgt", "opqtyb", "opweightb", "opstonewgtb", "disabled", "showinstkrep", "grpcode", "subgrpcode"},
        "salesm": {"slno", "tdate", "billno", "control", "status"},
        "salesd": {"slno", "code", "qty", "weight", "stonewgt", "cost", "amount", "jcode", "rate", "bcode"},
        "purchasem": {"slno", "tdate", "control", "status"},
        "purchased": {"slno", "code", "qty", "weight", "stwgt", "amount"}})
    return db


def test_calc_item_stock_opening_movement_closing():
    calc = StockCalculator(make_stock_db(), gilevel=1)
    st = calc.calc_item_stock("R1", "2026-06-01", "2026-06-30")
    # opening = items 100 + pre-period purchase 50 = 150 ; qty 10 + 5 = 15
    assert st["opwgt"] == Decimal("150.000")
    assert st["opqty"] == 15
    # period: received purchase 30, issued sale 20
    assert st["rcvdwgt"] == Decimal("30.000")
    assert st["issuedwgt"] == Decimal("20.000")
    # closing = 150 + 30 - 20 = 160 ; qty 15 + 3 - 2 = 16
    assert st["clwgt"] == Decimal("160.000")
    assert st["clqty"] == 16


def test_period_ledger_lists_items_with_txn():
    rows = StockPeriodLedgerService(make_stock_db()).ledger("2026-06-01", "2026-06-30", only_with_txn=True)
    assert len(rows) == 1 and rows[0]["code"] == "R1"
    assert rows[0]["clwgt"] == Decimal("160.000")


def test_stock_summary_costwise_vs_ratewise():
    db = make_stock_db()
    svc = StockSummaryService(db)
    cw = svc.transactions("2026-06-01", "2026-06-30", costwise=True)
    rw = svc.transactions("2026-06-01", "2026-06-30", costwise=False)
    # cost-wise gold sales amount = weight*cost = 20 * 9000 = 180000
    assert cw["gold_sales"]["amt"] == Decimal("180000.00")
    # rate-wise gold sales amount = salesd.amount = 200000
    assert rw["gold_sales"]["amt"] == Decimal("200000.00")
    assert cw["gold_sales"]["wgt"] == Decimal("20.000")
    # gold purchase (code<>OG) weight = 50 (pre-period) is outside the date range -> only 30 in range
    assert cw["gold_purch"]["wgt"] == Decimal("30.000")


def make_history_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE barcode (bcode INT, icode TEXT, qty INT, rate NUM, weight NUM, stweight NUM, tdate TEXT)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE salesm (slno INT, tdate TEXT, billno TEXT, control INT)"))
        c.execute(text("CREATE TABLE salesd (slno INT, bcode INT, weight NUM, stonewgt NUM, qty INT, rate NUM)"))
        c.execute(text("INSERT INTO barcode VALUES (501,'R1',1,5000,10.0,2.0,'2026-06-01')"))
        c.execute(text("INSERT INTO items VALUES ('R1','Ring')"))
        c.execute(text("INSERT INTO salesm VALUES (9,'2026-06-15','S9',1)"))
        c.execute(text("INSERT INTO salesd VALUES (9,501,10.0,2.0,1,5500)"))
    _bind(db, {"barcode": {"bcode", "icode", "qty", "rate", "weight", "stweight", "tdate"},
               "items": {"code", "name"},
               "salesm": {"slno", "tdate", "billno", "control"},
               "salesd": {"slno", "bcode", "weight", "stonewgt", "qty", "rate"}})
    return db


def test_barcode_history_timeline():
    svc = BarcodeHistoryService(make_history_db())
    rows = svc.history(501)
    txns = [r["transaction"] for r in rows]
    assert "Created" in txns and "Sales" in txns
    created = next(r for r in rows if r["transaction"] == "Created")
    assert created["weight"] == Decimal("10.000")
    info = svc.info(501)
    assert info["itemname"] == "Ring"
