"""Item Adjustment — weight-neutral validation + stock movement (from-/to+)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.item_adjustment.repo import ItemAdjustmentRepo
from python_gui.modules.item_adjustment.service import ItemAdjustmentError, ItemAdjustmentService

sqlite3.register_adapter(Decimal, str)
_ADJ = {"slno", "tdate", "fromcode", "fromqty", "fromwgt", "fromstwgt", "tocode", "toqty",
        "towgt", "tostwgt", "fromstktype", "tostktype", "particular", "control", "sno"}


def make():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE items (code TEXT, qty NUM, weight NUM, qtyb NUM, weightb NUM, stonewgt NUM, stonewgtb NUM)"))
        c.execute(text("CREATE TABLE itemsstk (code TEXT, stktype TEXT, qty NUM, weight NUM, stonewgt NUM, qtyb NUM, weightb NUM, stonewgtb NUM)"))
        c.execute(text("CREATE TABLE itemadj (" + ", ".join(f"{x} TEXT" for x in sorted(_ADJ)) + ")"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("INSERT INTO items (code, weight, weightb) VALUES ('R1', 100, 100), ('R2', 0, 0)"))
        c.execute(text("INSERT INTO itemsstk VALUES ('R1','G',1,100,0,1,100,0)"))
        c.execute(text("INSERT INTO itemsstk VALUES ('R2','G',0,0,0,0,0,0)"))
    db.table_exists = lambda t: t in ("items", "itemsstk", "itemadj", "generali")
    db.column_exists = lambda t, c: True
    db.columns = lambda t: _ADJ if t == "itemadj" else set()
    repo = ItemAdjustmentRepo(db)
    repo.item_exists = lambda code: code.strip().upper() in ("R1", "R2")
    pe = PostingEngine(db)
    pe.db.table_exists = db.table_exists
    pe.db.column_exists = lambda t, c: c == "slno"
    return db, ItemAdjustmentService(repo, pe)


def test_weight_neutral_required():
    _, svc = make()
    with pytest.raises(ItemAdjustmentError, match="positive and equal"):
        svc.save({"fromcode": "R1", "tocode": "R2", "fromwgt": "10", "towgt": "8"})


def test_missing_items():
    _, svc = make()
    with pytest.raises(ItemAdjustmentError, match="From and To item codes"):
        svc.save({"fromcode": "", "tocode": "R2"})


def test_transfer_moves_stock():
    db, svc = make()
    res = svc.save({"fromcode": "R1", "tocode": "R2", "fromwgt": "10", "towgt": "10",
                    "fromstktype": "G", "tostktype": "G", "tdate": "2026-06-17"})
    # itemsstk: R1 weight 100-10=90, R2 0+10=10
    r1 = db.scalar("SELECT weight FROM itemsstk WHERE code='R1' AND stktype='G'")
    r2 = db.scalar("SELECT weight FROM itemsstk WHERE code='R2' AND stktype='G'")
    assert Decimal(str(r1)) == Decimal("90") and Decimal(str(r2)) == Decimal("10")
    # items table likewise
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='R1'"))) == Decimal("90")
    # itemadj row recorded
    assert db.fetchone("SELECT 1 FROM itemadj WHERE slno = :s", {"s": res["slno"]}) is not None


def test_AL_code_exempt_from_weight_rule():
    db, svc = make()
    # 'AL' (add/less) lets a one-sided adjustment through
    res = svc.save({"fromcode": "AL", "tocode": "R2", "fromwgt": "0", "towgt": "5",
                    "tostktype": "G", "tdate": "2026-06-17"})
    assert Decimal(str(db.scalar("SELECT weight FROM itemsstk WHERE code='R2' AND stktype='G'"))) == Decimal("5")
