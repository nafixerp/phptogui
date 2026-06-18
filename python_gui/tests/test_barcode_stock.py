"""Barcode Entry CRUD + PB flag quirks, and Stock Register aggregation."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.barcode_entry.repo import BarcodeRepo
from python_gui.modules.barcode_entry.service import BarcodeError, BarcodeService
from python_gui.modules.stock_register.service import StockRegisterService

sqlite3.register_adapter(Decimal, str)

_BC_COLS = {"bcode", "icode", "qty", "weight", "qtype", "wastage", "mc", "mcrate", "rate",
            "docno", "smithcode", "counter", "stk", "stkinnos", "nodisc", "status", "tdate",
            "control", "costamt", "sizemodel", "weight2"}


def make_bc():
    db = Database()
    db._engine = create_engine("sqlite://", future=True)
    cols = ", ".join(f"{c} TEXT" for c in sorted(_BC_COLS - {"bcode"}))
    with db._engine.begin() as c:
        c.execute(text(f"CREATE TABLE barcode (bcode INT PRIMARY KEY, {cols})"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT, wastage NUM, mcharge NUM, vaperc NUM, stkinnos TEXT, nodisc TEXT, stickerwgt NUM, defquality TEXT, subgrpcode TEXT)"))
        c.execute(text("CREATE TABLE salesd (bcode INT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("INSERT INTO items VALUES ('GOLD22','22K Gold',8,150,5,'N','',0,'22K','RING')"))
    repo = BarcodeRepo(db)
    repo.has_table = lambda t="barcode": t in ("barcode", "items", "salesd", "generali")
    repo.columns = lambda: _BC_COLS
    repo.db.table_exists = lambda t: t in ("barcode", "items", "salesd", "generali")
    return db, BarcodeService(repo)


def test_next_barcode_starts_at_100001():
    _, svc = make_bc()
    assert svc.next_barcode() == 100001


def test_add_barcode_pb_flag_quirks():
    db, svc = make_bc()
    svc.save({"bcode": "100001", "icode": "GOLD22", "qty": "1", "weight": "10",
              "sold": "Y", "stkinnos": "N", "nodisc": "Y"}, "add")
    row = db.fetchone("SELECT stk, stkinnos, nodisc, status FROM barcode WHERE bcode=100001")
    assert row["stk"] == "N"        # sold='Y' -> stk='N'
    assert row["nodisc"] == "N"     # nodisc='Y' -> stored 'N'
    assert row["status"] == "N"
    assert svc.next_barcode() == 100002


def test_add_validations():
    _, svc = make_bc()
    with pytest.raises(BarcodeError, match="Item code is required"):
        svc.save({"bcode": "1", "icode": "", "qty": "1"}, "add")
    with pytest.raises(BarcodeError, match="greater than zero"):
        svc.save({"bcode": "1", "icode": "X", "qty": "0"}, "add")


def test_duplicate_add_blocked():
    _, svc = make_bc()
    svc.save({"bcode": "100001", "icode": "GOLD22", "qty": "1", "weight": "10"}, "add")
    with pytest.raises(BarcodeError, match="already exists"):
        svc.save({"bcode": "100001", "icode": "GOLD22", "qty": "1"}, "add")


def test_delete_blocked_when_sold():
    db, svc = make_bc()
    svc.save({"bcode": "100001", "icode": "GOLD22", "qty": "1", "weight": "10"}, "add")
    db.execute("INSERT INTO salesd (bcode) VALUES (100001)")
    with pytest.raises(BarcodeError, match="already sold"):
        svc.delete(100001)


def test_load_item_populates():
    _, svc = make_bc()
    item = svc.load_item("gold22")
    assert item["name"] == "22K Gold" and str(item["wastage"]) in ("8", "8.0")


# -- Stock Register ----------------------------------------------------------

def test_stock_register_opening_plus_movements():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT, itype TEXT, grpcode TEXT)"))
        c.execute(text("CREATE TABLE itemsstk (code TEXT, qty NUM, weight NUM)"))
        for t, m in [("purchased", "purchasem"), ("salesd", "salesm")]:
            c.execute(text(f"CREATE TABLE {t} (slno INT, code TEXT, qty NUM, weight NUM)"))
            c.execute(text(f"CREATE TABLE {m} (slno INT, tdate TEXT, control INT)"))
        c.execute(text("INSERT INTO items VALUES ('R1','Ring','G','RING')"))
        c.execute(text("INSERT INTO itemsstk VALUES ('R1', 5, 50)"))           # opening
        c.execute(text("INSERT INTO purchasem VALUES (1,'2026-06-10',1)"))
        c.execute(text("INSERT INTO purchased VALUES (1,'R1', 3, 30)"))         # +30
        c.execute(text("INSERT INTO salesm VALUES (2,'2026-06-11',1)"))
        c.execute(text("INSERT INTO salesd VALUES (2,'R1', 2, 20)"))            # -20
    db.table_exists = lambda t: t in ("items", "itemsstk", "purchased", "purchasem", "salesd", "salesm")
    rows = StockRegisterService(db).summary("2026-06-01", "2026-06-30")
    r = next(x for x in rows if x["code"] == "R1")
    assert r["op_weight"] == Decimal("50.000")
    assert r["close_weight"] == Decimal("60.000")   # 50 + 30 - 20
