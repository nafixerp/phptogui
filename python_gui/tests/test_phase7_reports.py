"""Phase 7: barcode profit, marked list, diamond/stone stock, counter issue, reorder."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.barcode_profit.service import BarcodeProfitService
from python_gui.modules.counter_issue.service import CounterIssueService
from python_gui.modules.diamond_stone_stock.service import DiamondStoneStockService
from python_gui.modules.marked_list.service import MarkedListService
from python_gui.modules.reorder.service import ReorderService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


# ── barcode profit ────────────────────────────────────────────────────────────

def make_profit_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE salesm (slno INT, tdate TEXT, billno TEXT, control INT)"))
        c.execute(text("CREATE TABLE salesd (slno INT, code TEXT, bcode INT, qty INT, weight NUM, amount NUM, stonewgt NUM, stoneprice NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT, grpcode TEXT)"))
        c.execute(text("CREATE TABLE barcode (bcode INT, cost NUM, costperc NUM, costamt NUM, coststone NUM)"))
        c.execute(text("INSERT INTO salesm VALUES (1,'2026-06-10','S1',1)"))
        c.execute(text("INSERT INTO items VALUES ('R1','Ring','G')"))
        # line A: bc.costamt>0 -> costamt=4000, profit=10000-4000
        c.execute(text("INSERT INTO salesd VALUES (1,'R1',101,1,10.0,10000,2.0,500)"))
        c.execute(text("INSERT INTO barcode VALUES (101,0,0,4000,300)"))
        # line B: cost>0 -> costamt=round((wgt-stwgt)*cost)= (8-1)*900=6300
        c.execute(text("INSERT INTO salesd VALUES (1,'R1',102,1,8.0,9000,1.0,0)"))
        c.execute(text("INSERT INTO barcode VALUES (102,900,0,0,0)"))
    _bind(db, {"salesm": {"slno", "tdate", "billno", "control"},
               "salesd": {"slno", "code", "bcode", "qty", "weight", "amount", "stonewgt", "stoneprice"},
               "items": {"code", "name", "grpcode"},
               "barcode": {"bcode", "cost", "costperc", "costamt", "coststone"}})
    return db


def test_barcode_profit_cost_rules():
    res = BarcodeProfitService(make_profit_db()).report("2026-06-01", "2026-06-30")
    rows = {r["bcode"]: r for r in res["rows"]}
    assert rows[101]["costamt"] == Decimal("4000.00")
    assert rows[101]["profit"] == Decimal("6000.00")
    assert rows[102]["costamt"] == Decimal("6300.00")
    assert rows[102]["profit"] == Decimal("2700.00")
    assert res["totals"]["profit"] == Decimal("8700.00")


# ── marked list ─────────────────────────────────────────────────────────────

def make_marked_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE salesm (slno INT, tdate TEXT, billno TEXT, control INT, smcode TEXT)"))
        c.execute(text("CREATE TABLE salesd (slno INT, code TEXT, bcode INT, qty INT, weight NUM, amount NUM, stonewgt NUM, mark TEXT, rmno TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT, itype TEXT, ornament TEXT)"))
        c.execute(text("INSERT INTO salesm VALUES (1,'2026-06-10','S1',1,'SM1')"))
        c.execute(text("INSERT INTO items VALUES ('R1','Ring','G','Y')"))
        c.execute(text("INSERT INTO salesd VALUES (1,'R1',1,1,10.0,10000,2.0,'Y','','')"))
        c.execute(text("INSERT INTO salesd VALUES (1,'R1',2,1,5.0,5000,1.0,'N','','Custom')"))
    _bind(db, {"salesm": {"slno", "tdate", "billno", "control", "smcode"},
               "salesd": {"slno", "code", "bcode", "qty", "weight", "amount", "stonewgt", "mark", "rmno", "name"},
               "items": {"code", "name", "itype", "ornament"}})
    return db


def test_marked_list_filter_and_gross():
    svc = MarkedListService(make_marked_db())
    allrows = svc.report("2026-06-01", "2026-06-30")
    assert len(allrows) == 2
    assert allrows[0]["grosswgt"] == Decimal("8.000")  # 10 - 2
    marked = svc.report("2026-06-01", "2026-06-30", marked="Y")
    assert len(marked) == 1 and marked[0]["mark"] == "Y"
    assert svc.report("2026-06-01", "2026-06-30", marked="N")[0]["displayname"] == "Custom"


# ── diamond / stone stock ────────────────────────────────────────────────────

def make_stock_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT, disabled INT, showinstkrep TEXT, dmdplt TEXT, grpcode TEXT)"))
        c.execute(text("CREATE TABLE barcode (bcode INT, icode TEXT, weight NUM, stweight NUM, stk TEXT)"))
        c.execute(text("INSERT INTO items VALUES ('D1','Diamond Ring',0,'Y','D','G')"))
        c.execute(text("INSERT INTO items VALUES ('D2','Empty',0,'Y','D','G')"))
        c.execute(text("INSERT INTO barcode VALUES (1,'D1',10.0,3.0,'Y')"))
        c.execute(text("INSERT INTO barcode VALUES (2,'D1',5.0,1.0,'Y')"))
        c.execute(text("INSERT INTO barcode VALUES (3,'D1',9.0,2.0,'N')"))  # not in stock, excluded
    _bind(db, {"items": {"code", "name", "disabled", "showinstkrep", "dmdplt", "grpcode"},
               "barcode": {"bcode", "icode", "weight", "stweight", "stk"}})
    return db


def test_diamond_stone_stock_summary():
    rows = DiamondStoneStockService(make_stock_db()).summary("Diamond")
    by = {r["code"]: r for r in rows}
    assert "D2" not in by  # no stock -> dropped
    assert by["D1"]["nos"] == 2
    assert by["D1"]["grosswgt"] == Decimal("15.000")
    assert by["D1"]["goldwgt"] == Decimal("11.000")  # 15 - 4 stone


# ── counter issue ───────────────────────────────────────────────────────────

def make_counter_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE counter (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE barcode (bcode INT, icode TEXT, qty INT, weight NUM, stweight NUM, dmdwgt NUM, tdate TEXT, stk TEXT, counter TEXT, rate NUM, cost NUM)"))
        c.execute(text("INSERT INTO counter VALUES ('C1','Front Counter')"))
        c.execute(text("INSERT INTO items VALUES ('R1','Ring')"))
        c.execute(text("INSERT INTO barcode VALUES (1,'R1',1,10.0,2.0,0,'2026-06-01','Y','C1',5000,4000)"))
        c.execute(text("INSERT INTO barcode VALUES (2,'R1',1,6.0,1.0,0,'2026-06-01','Y','C2',5000,4000)"))
    _bind(db, {"counter": {"code", "name"}, "items": {"code", "name"},
               "barcode": {"bcode", "icode", "qty", "weight", "stweight", "dmdwgt", "tdate", "stk", "counter", "rate", "cost"}})
    return db


def test_counter_issue_by_counter():
    res = CounterIssueService(make_counter_db()).by_counter("C1")
    assert res["counterName"] == "Front Counter"
    assert len(res["rows"]) == 1
    assert res["rows"][0]["netwgt"] == Decimal("8.000")


# ── reorder ─────────────────────────────────────────────────────────────────

def make_reorder_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE rotable (code TEXT, model TEXT, size TEXT, weight1 NUM, weight2 NUM, minqty INT, maxqty INT)"))
        c.execute(text("CREATE TABLE models (mtype TEXT, name TEXT)"))
        c.execute(text("INSERT INTO items VALUES ('R1','Ring')"))
    _bind(db, {"items": {"code", "name"},
               "rotable": {"code", "model", "size", "weight1", "weight2", "minqty", "maxqty"},
               "models": {"mtype", "name"}})
    return db


def test_reorder_save_replaces_and_registers_models():
    db = make_reorder_db()
    svc = ReorderService(db)
    svc.save("R1", [
        {"model": "A", "size": "S1", "weight1": 1.0, "weight2": 2.0, "minqty": 3, "maxqty": 9},
        {"model": "", "size": "", "weight1": 0, "weight2": 0, "minqty": 1, "maxqty": 1},  # skipped
    ])
    res = svc.get_item("r1")
    assert res is not None and len(res["levels"]) == 1
    assert res["levels"][0]["model"] == "A"
    # model + size registered
    assert int(db.scalar("SELECT COUNT(*) FROM models WHERE mtype='M' AND name='A'")) == 1
    assert int(db.scalar("SELECT COUNT(*) FROM models WHERE mtype='S' AND name='S1'")) == 1
    # re-save replaces
    svc.save("R1", [{"model": "B", "size": "", "weight1": 2.0, "weight2": 3.0, "minqty": 0, "maxqty": 0}])
    assert {lv["model"] for lv in svc.get_item("R1")["levels"]} == {"B"}
