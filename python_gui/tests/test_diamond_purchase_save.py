"""Bucket B: diamond purchase save — purchasem/purchased/purchased_dmddet + stock + PL daybook."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine
from python_gui.modules.diamond_purchase.service import (
    DiamondPurchaseSaveError,
    DiamondPurchaseSaveService,
)

sqlite3.register_adapter(Decimal, str)

_PM = {"slno", "docno", "billno", "suppcode", "name", "billamt", "netamt", "taxamt", "discount",
       "pr", "dmd", "control", "tdate", "ttime", "status", "ic"}
_PD = {"slno", "code", "qty", "weight", "rate", "amount", "cost", "stwgt", "stprice", "sno",
       "stktype", "mcharge", "touch", "bcode", "dmdamt", "dmdwgt"}
_DD = {"slno", "prow", "sno", "code", "sttype", "stcolor", "stsize", "stcut", "stsettype",
       "pcs", "carats", "rate", "amount"}
_DB = {"slno", "tdate", "accode", "amount", "control", "sno", "opaccode", "vtype"}
_DP = {"slno", "tdate", "control", "particular", "vchno"}
_ITEMS = {"code", "qty", "weight", "stonewgt", "qtyb", "weightb", "stonewgtb"}


def make_engine():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE purchasem (slno INT, docno TEXT, billno TEXT, suppcode TEXT, name TEXT, billamt NUM, "
                       "netamt NUM, taxamt NUM, discount NUM, pr TEXT, dmd TEXT, control INT, tdate TEXT, ttime TEXT, status INT, ic TEXT)"))
        c.execute(text("CREATE TABLE purchased (slno INT, code TEXT, qty INT, weight NUM, rate NUM, amount NUM, cost NUM, "
                       "stwgt NUM, stprice NUM, sno INT, stktype TEXT, mcharge NUM, touch NUM, bcode TEXT, dmdamt NUM, dmdwgt NUM)"))
        c.execute(text("CREATE TABLE purchased_dmddet (slno INT, prow INT, sno INT, code TEXT, sttype TEXT, stcolor TEXT, "
                       "stsize TEXT, stcut TEXT, stsettype TEXT, pcs INT, carats NUM, rate NUM, amount NUM)"))
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, sno INT, opaccode TEXT, vtype TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, tdate TEXT, control INT, particular TEXT, vchno TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)"))
        c.execute(text("CREATE TABLE generals (code TEXT PRIMARY KEY, cvalue TEXT)"))
        c.execute(text("CREATE TABLE items (code TEXT, qty INT, weight NUM, stonewgt NUM, qtyb INT, weightb NUM, stonewgtb NUM)"))
        c.execute(text("CREATE TABLE delpart (slno INT)"))
        c.execute(text("INSERT INTO generals VALUES ('DPBPREF','DP')"))
        c.execute(text("INSERT INTO items VALUES ('RING01',0,0,0,0,0,0)"))
    pe = PostingEngine(db)
    cmap = {"purchasem": _PM, "purchased": _PD, "purchased_dmddet": _DD, "daybook": _DB,
            "daybookpart": _DP, "items": _ITEMS, "generali": {"code", "cvalue"},
            "generals": {"code", "cvalue"}, "delpart": {"slno"}}
    tabs = set(cmap)
    pe.db.table_exists = lambda t: t in tabs
    pe.db.column_exists = lambda t, c: c in cmap.get(t, set())
    pe.db.columns = lambda t: cmap.get(t, set())
    return db, pe


def test_save_writes_diamond_bill_with_stones_and_stock():
    db, pe = make_engine()
    svc = DiamondPurchaseSaveService(pe, control=1)
    res = svc.save(
        header={"suppcode": "s1", "name": "ACME", "billno": "SB1"},
        items=[{"code": "ring01", "qty": 1, "weight": 5.0, "amount": 50000, "rate": 6000, "stwgt": 0.5,
                "stktype": "",
                "dmd_rows": [{"stcode": "DIA", "sttype": "VVS", "pcs": 4, "carats": 0.52, "rate": 90000, "amount": 46800},
                             {"stcode": "DIA", "pcs": 0, "carats": 0}]}],  # second sub-row skipped (no pcs/carats)
        amounts={"supplier_code": "S1", "net_total": 50000, "bill_total": 50000, "paid_amount": 50000})
    assert res["docno"].startswith("DP") and res["items"] == 1
    # purchasem flagged diamond
    pm = db.fetchone("SELECT pr, dmd, billamt FROM purchasem WHERE slno=:s", {"s": res["slno"]})
    assert pm["pr"] == "P" and pm["dmd"] == "Y"
    assert Decimal(str(pm["billamt"])) == Decimal("50000.00")
    # purchased row + cost = amount/weight
    pd = db.fetchone("SELECT cost FROM purchased WHERE slno=:s", {"s": res["slno"]})
    assert Decimal(str(pd["cost"])) == Decimal("10000.00")
    # one valid stone sub-row (the empty one skipped)
    assert int(db.scalar("SELECT COUNT(*) FROM purchased_dmddet WHERE slno=:s", {"s": res["slno"]})) == 1
    assert int(db.scalar("SELECT prow FROM purchased_dmddet WHERE slno=:s", {"s": res["slno"]})) == 1
    # stock increased by purchase
    assert Decimal(str(db.scalar("SELECT weight FROM items WHERE code='RING01'"))) == Decimal("5.000")
    assert int(db.scalar("SELECT qty FROM items WHERE code='RING01'")) == 1


def test_save_daybook_balanced():
    db, pe = make_engine()
    svc = DiamondPurchaseSaveService(pe, control=1)
    res = svc.save(
        header={"suppcode": "S1", "name": "ACME"},
        items=[{"code": "RING01", "qty": 1, "weight": 5.0, "amount": 50000}],
        amounts={"supplier_code": "S1", "bill_total": 50000, "net_total": 50000, "paid_amount": 50000})
    assert res["balanced"] is True
    total = sum(Decimal(str(r["amount"])) for r in
                db.fetchall("SELECT amount FROM daybook WHERE slno=:s", {"s": res["slno"]}))
    assert total == Decimal("0.00")


def test_save_validations():
    db, pe = make_engine()
    svc = DiamondPurchaseSaveService(pe)
    with pytest.raises(DiamondPurchaseSaveError):
        svc.save(header={"suppcode": ""}, items=[{"code": "X", "amount": 1}])
    with pytest.raises(DiamondPurchaseSaveError):
        svc.save(header={"suppcode": "S1"}, items=[{"code": ""}])
