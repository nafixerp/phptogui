"""Diamond Purchase register — list, load with stone sub-rows, doc-no preview."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.diamond_purchase.service import DiamondPurchaseService

sqlite3.register_adapter(Decimal, str)

_PM = {"slno", "docno", "billno", "tdate", "suppcode", "name", "billamt",
       "netamt", "control", "pr", "dmd"}
_PD = {"slno", "sno", "code", "qty", "weight", "rate", "amount"}
_DD = {"slno", "prow", "sno", "code", "sttype", "stcolor", "stsize", "stcut",
       "stsettype", "pcs", "carats", "rate", "amount"}


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE purchasem (slno INT, docno TEXT, billno TEXT, tdate TEXT, suppcode TEXT, "
                       "name TEXT, billamt NUM, netamt NUM, control INT, pr TEXT, dmd TEXT)"))
        c.execute(text("CREATE TABLE purchased (slno INT, sno INT, code TEXT, qty INT, weight NUM, rate NUM, amount NUM)"))
        c.execute(text("CREATE TABLE purchased_dmddet (slno INT, prow INT, sno INT, code TEXT, sttype TEXT, stcolor TEXT, "
                       "stsize TEXT, stcut TEXT, stsettype TEXT, pcs INT, carats NUM, rate NUM, amount NUM)"))
        c.execute(text("CREATE TABLE generals (code TEXT, cvalue TEXT)"))
        c.execute(text("CREATE TABLE generali (code TEXT, cvalue INT)"))
        # diamond bill (pr=P, dmd=Y) + a regular purchase (dmd NULL) which must be excluded
        c.execute(text("INSERT INTO purchasem VALUES (10,'DP001','SB1','2026-06-10','S1','ACME',50000,51000,1,'P','Y')"))
        c.execute(text("INSERT INTO purchasem VALUES (11,'P002','SB2','2026-06-12','S1','ACME',9000,9000,1,'P',NULL)"))
        c.execute(text("INSERT INTO purchased VALUES (10,1,'RING01',1,5.250,8000,42000)"))
        c.execute(text("INSERT INTO purchased VALUES (10,2,'RING02',1,2.000,4000,8000)"))
        # stone sub-rows for prow 1 (RING01)
        c.execute(text("INSERT INTO purchased_dmddet VALUES (10,1,1,'DIA','VVS','D','5','RND','PR',4,0.520,90000,46800)"))
        c.execute(text("INSERT INTO purchased_dmddet VALUES (10,1,2,'DIA','VS','E','3','RND','PR',2,0.180,80000,14400)"))
        c.execute(text("INSERT INTO generals VALUES ('DPBPREF','DP')"))
        c.execute(text("INSERT INTO generali VALUES ('DPURCHASEB',7)"))
    _tabs = {"purchasem", "purchased", "purchased_dmddet", "generals", "generali"}
    _colmap = {"purchasem": _PM, "purchased": _PD, "purchased_dmddet": _DD,
               "generals": {"code", "cvalue"}, "generali": {"code", "cvalue"}}
    db.table_exists = lambda t: t in _tabs
    db.column_exists = lambda t, col: col in _colmap.get(t, set())
    db.columns = lambda t: _colmap.get(t, set())
    return db


def test_list_only_diamond_bills():
    rows = DiamondPurchaseService(make_db()).list_bills("2026-06-01", "2026-06-30")
    # regular purchase (dmd NULL) excluded -> only DP001
    assert {r["docno"] for r in rows} == {"DP001"}
    assert float(rows[0]["netamt"]) == 51000.0


def test_get_bill_with_stone_rows():
    bill = DiamondPurchaseService(make_db()).get_bill("dp001")  # case-insensitive
    assert bill is not None
    items = bill["items"]
    assert [i["code"] for i in items] == ["RING01", "RING02"]
    # stone rows attach to the first item (prow 1); second item has none
    assert len(items[0]["dmd_rows"]) == 2
    assert items[1]["dmd_rows"] == []
    assert items[0]["dmd_rows"][0]["carats"] == Decimal("0.520")
    assert items[0]["dmd_rows"][0]["amount"] == Decimal("46800.00")


def test_get_bill_rejects_non_diamond():
    assert DiamondPurchaseService(make_db()).get_bill("P002") is None


def test_next_doc_no_preview():
    # prefix DP + (counter 7 + 1) padded to 5 -> DP00008
    assert DiamondPurchaseService(make_db()).next_doc_no() == "DP00008"
