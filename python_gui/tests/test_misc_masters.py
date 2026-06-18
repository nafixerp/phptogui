"""Gift Table, Wastage Table, Point Card masters."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.gift_table.service import GiftTableService
from python_gui.modules.point_card.service import PointCardService
from python_gui.modules.wastage_table.service import WastageTableService

sqlite3.register_adapter(Decimal, str)


def db_with(ddl):
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        for s in ddl:
            c.execute(text(s))
    return db


def test_gift_table_upsert_and_rename():
    db = db_with(["CREATE TABLE gifttable (points INT PRIMARY KEY, particulars TEXT)"])
    db.table_exists = lambda t: t == "gifttable"
    svc = GiftTableService(db)
    svc.save("100", "Silver Coin")
    svc.save("100", "Gold Coin")                  # update
    assert svc.list()[0]["particulars"] == "Gold Coin"
    svc.save("200", "Pendant", orig_points="100")  # rename 100 -> 200
    pts = [r["points"] for r in svc.list()]
    assert pts == [200]


def test_wastage_bulk_replace_skips_zero():
    db = db_with(["CREATE TABLE wstgtable (code TEXT, weight1 NUM, weight2 NUM, wastage NUM, perc NUM, iqtype TEXT)"])
    db.table_exists = lambda t: t == "wstgtable"
    svc = WastageTableService(db)
    msg = svc.save("RING", "22K", [
        {"weight1": "0", "weight2": "10", "wastage": "8", "perc": "2"},
        {"weight1": "0", "weight2": "0", "wastage": "0"},   # skipped
    ])
    rows = svc.get_for_item("RING", "22K")
    assert len(rows) == 1 and "1 slab" in msg
    svc.save("RING", "22K", [{"weight1": "10", "weight2": "20", "wastage": "6"}])  # replace
    assert len(svc.get_for_item("RING", "22K")) == 1


def test_point_card_upsert():
    db = db_with(["CREATE TABLE pcardtable (pcard TEXT, isubgrp TEXT, pointbasedon TEXT, valuefor1point NUM, valueperpoint NUM, minsalesamt NUM, rounddown TEXT)"])
    db.table_exists = lambda t: t == "pcardtable"
    svc = PointCardService(db)
    svc.save({"pcard": "PC1", "isubgrp": "RING", "valueperpoint": "10", "minsalesamt": "1000"})
    svc.save({"pcard": "PC1", "isubgrp": "RING", "valueperpoint": "20"})   # update same key
    rows = svc.list()
    assert len(rows) == 1 and Decimal(str(rows[0]["valueperpoint"])) == Decimal("20")
    svc.save({"pcard": "PC1", "isubgrp": "CHAIN", "valueperpoint": "5"})   # different subgrp -> new row
    assert len(svc.list()) == 2
