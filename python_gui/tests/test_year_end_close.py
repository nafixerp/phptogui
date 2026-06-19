"""Pending: year-end account close (flag-driven destructive close + roll-forward)."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.year_end_close.service import YearEndCloseError, YearEndCloseService

sqlite3.register_adapter(Decimal, str)

_COLMAP = {
    "salesm": {"slno", "tdate", "status", "control", "custcode"},
    "salesd": {"slno", "code", "qty", "weight"},
    "purchasem": {"slno", "tdate", "status", "control", "pr", "suppcode"},
    "purchased": {"slno", "code", "qty", "weight"},
    "repairm": {"slno", "tdate", "status", "control"},
    "repaird": {"slno", "code", "qty", "weight", "givrec"},
    "smithm": {"slno", "tdate", "control"},
    "smithd": {"slno", "code", "qty", "weight", "givrec"},
    "kuricolln": {"slno", "tdate", "control", "closed", "code"},
    "daybook": {"slno", "tdate", "accode", "amount", "control"},
    "daybookpart": {"slno", "particular"},
    "accountm": {"accode", "opbal", "opbalb", "actype1"},
    "clients": {"code", "opbalance", "opbalanceb", "addr1", "mobile"},
    "items": {"code", "opqty", "opqtyb", "opweight", "opweightb",
              "opstonewgt", "opstonewgtb", "stonemarg"},
    "barcode": {"bcode", "stk"},
}


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE salesm (slno INT, tdate TEXT, status INT, control INT, custcode TEXT)"))
        c.execute(text("CREATE TABLE salesd (slno INT, code TEXT, qty INT, weight NUM)"))
        c.execute(text("CREATE TABLE purchasem (slno INT, tdate TEXT, status INT, control INT, pr TEXT, suppcode TEXT)"))
        c.execute(text("CREATE TABLE purchased (slno INT, code TEXT, qty INT, weight NUM)"))
        c.execute(text("CREATE TABLE repairm (slno INT, tdate TEXT, status INT, control INT)"))
        c.execute(text("CREATE TABLE repaird (slno INT, code TEXT, qty INT, weight NUM, givrec TEXT)"))
        c.execute(text("CREATE TABLE smithm (slno INT, tdate TEXT, control INT)"))
        c.execute(text("CREATE TABLE smithd (slno INT, code TEXT, qty INT, weight NUM, givrec TEXT)"))
        c.execute(text("CREATE TABLE kuricolln (slno INT, tdate TEXT, control INT, closed TEXT, code TEXT)"))
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, particular TEXT)"))
        c.execute(text("CREATE TABLE accountm (accode TEXT, opbal NUM, opbalb NUM, actype1 TEXT)"))
        c.execute(text("CREATE TABLE clients (code TEXT, opbalance NUM, opbalanceb NUM, addr1 TEXT, mobile TEXT)"))
        c.execute(text("CREATE TABLE items (code TEXT, opqty INT, opqtyb INT, opweight NUM, opweightb NUM, opstonewgt NUM, opstonewgtb NUM, stonemarg NUM)"))
        c.execute(text("CREATE TABLE barcode (bcode TEXT, stk TEXT)"))
    db.table_exists = lambda t: t in _COLMAP
    db.column_exists = lambda t, col: col in _COLMAP.get(t, set())
    db.columns = lambda t: _COLMAP.get(t, set())
    return db


def _seed(db):
    with db._engine.begin() as c:
        # cash sale (status 3) on/before date, credit sale (status 1) after
        c.execute(text("INSERT INTO salesm VALUES (1,'2024-01-10',3,1,'C1')"))
        c.execute(text("INSERT INTO salesm VALUES (2,'2024-12-31',1,1,'C2')"))
        c.execute(text("INSERT INTO salesd VALUES (1,'IT1',2,10)"))
        c.execute(text("INSERT INTO salesd VALUES (2,'IT1',1,5)"))
        c.execute(text("INSERT INTO repairm VALUES (1,'2024-02-01',1,1)"))  # pending
        c.execute(text("INSERT INTO repairm VALUES (2,'2024-02-01',3,1)"))  # done
        c.execute(text("INSERT INTO repaird VALUES (1,'R1',1,3,'R')"))
        c.execute(text("INSERT INTO repaird VALUES (2,'R1',1,3,'R')"))
        c.execute(text("INSERT INTO kuricolln VALUES (1,'2024-03-01',1,'N','K1')"))
        c.execute(text("INSERT INTO kuricolln VALUES (2,'2025-07-01',1,'N','K1')"))  # after date
        c.execute(text("INSERT INTO accountm VALUES ('A1',100,50,'A')"))
        c.execute(text("INSERT INTO accountm VALUES ('IE1',0,0,'R')"))
        c.execute(text("INSERT INTO daybook VALUES (1,'2024-05-01','A1',200,1)"))
        c.execute(text("INSERT INTO daybook VALUES (2,'2024-05-01','A1',300,2)"))
        c.execute(text("INSERT INTO daybookpart VALUES (1,'x')"))
        c.execute(text("INSERT INTO clients VALUES ('A1',0,0,'addr','9999')"))


DATE = "2024-12-31"


def test_delete_cash_sales_only():
    db = make_db(); _seed(db)
    svc = YearEndCloseService(db)
    res = svc.close_accounts(DATE, {"chsales": True})
    # cash sale slno=1 deleted (and its detail), credit sale slno=2 survives
    assert res["summary"]["cash_sales"] == 1
    assert int(db.scalar("SELECT COUNT(*) FROM salesm")) == 1
    assert db.scalar("SELECT slno FROM salesm") == 2
    assert int(db.scalar("SELECT COUNT(*) FROM salesd WHERE slno=1")) == 0


def test_delete_pending_vs_done_repair():
    db = make_db(); _seed(db)
    svc = YearEndCloseService(db)
    res = svc.close_accounts(DATE, {"reppend": True})
    assert res["summary"]["pending_repair"] == 1
    assert {r["slno"] for r in db.fetchall("SELECT slno FROM repairm")} == {2}
    assert int(db.scalar("SELECT COUNT(*) FROM repaird WHERE slno=1")) == 0


def test_kuri_marks_closed_when_not_deleting():
    db = make_db(); _seed(db)
    YearEndCloseService(db).close_accounts(DATE, {"deldaybookentries": False})
    # not deleting kuri -> rows <= date marked closed='Y', later row untouched
    assert db.scalar("SELECT closed FROM kuricolln WHERE slno=1") == "Y"
    assert db.scalar("SELECT closed FROM kuricolln WHERE slno=2") == "N"


def test_kuri_delete_when_flagged():
    db = make_db(); _seed(db)
    res = YearEndCloseService(db).close_accounts(DATE, {"kuricolln": True})
    assert res["summary"]["kuri"] == 1
    assert {r["slno"] for r in db.fetchall("SELECT slno FROM kuricolln")} == {2}


def test_daybook_roll_forward_and_delete():
    db = make_db(); _seed(db)
    res = YearEndCloseService(db).close_accounts(DATE, {"deldaybookentries": True})
    # A1 opbal = 100 + sum(control=1)=200 -> 300 ; opbalb = 50 + sum(control=2)=300 -> 350
    assert Decimal(str(db.scalar("SELECT opbal FROM accountm WHERE accode='A1'"))) == Decimal("300")
    assert Decimal(str(db.scalar("SELECT opbalb FROM accountm WHERE accode='A1'"))) == Decimal("350")
    # clients opbalance synced from accountm
    assert Decimal(str(db.scalar("SELECT opbalance FROM clients WHERE code='A1'"))) == Decimal("300")
    # daybook + parts deleted
    assert int(db.scalar("SELECT COUNT(*) FROM daybook")) == 0
    assert int(db.scalar("SELECT COUNT(*) FROM daybookpart")) == 0


def test_keepbills_filters_daybook_delete():
    db = make_db(); _seed(db)
    YearEndCloseService(db).close_accounts(DATE, {"deldaybookentries": True, "keepbills": True})
    # keepbills -> only control=2 rows deleted; control=1 row survives
    rows = {r["slno"] for r in db.fetchall("SELECT slno FROM daybook")}
    assert rows == {1}


def test_reset_account_type_balances_ie():
    db = make_db(); _seed(db)
    with db._engine.begin() as c:
        c.execute(text("UPDATE accountm SET opbal=999, opbalb=999 WHERE accode='IE1'"))
    YearEndCloseService(db).close_accounts(DATE, {"initopbalie": True})
    assert Decimal(str(db.scalar("SELECT opbal FROM accountm WHERE accode='IE1'"))) == Decimal("0")
    # asset account untouched by IE reset
    assert Decimal(str(db.scalar("SELECT opbal FROM accountm WHERE accode='A1'"))) == Decimal("100")


def test_remove_addr():
    db = make_db(); _seed(db)
    YearEndCloseService(db).close_accounts(DATE, {"removeaddr": True})
    assert db.scalar("SELECT addr1 FROM clients WHERE code='A1'") == ""
    assert db.scalar("SELECT mobile FROM clients WHERE code='A1'") == ""


def test_delete_outstock_barcodes():
    db = make_db(); _seed(db)
    with db._engine.begin() as c:
        c.execute(text("INSERT INTO barcode VALUES ('B1','N')"))
        c.execute(text("INSERT INTO barcode VALUES ('B2','Y')"))
    res = YearEndCloseService(db).close_accounts(DATE, {"deloutstockbarcode": True})
    assert res["summary"]["barcode"] == 1
    assert {r["bcode"] for r in db.fetchall("SELECT bcode FROM barcode")} == {"B2"}


def test_stock_roll_forward_sales():
    db = make_db(); _seed(db)
    with db._engine.begin() as c:
        c.execute(text("INSERT INTO items VALUES ('IT1',0,10,0,100,0,0,0)"))
    # keepbills keeps control=2 rows on delete (our cash sale slno=1 is control=1, so it
    # survives the purge) and the roll-forward then deducts its sold qty/weight from opening.
    YearEndCloseService(db).close_accounts(DATE, {"chsales": True, "keepbills": True})
    assert int(db.scalar("SELECT COUNT(*) FROM salesm WHERE slno=1")) == 1  # not deleted
    assert Decimal(str(db.scalar("SELECT opqtyb FROM items WHERE code='IT1'"))) == Decimal("8")
    assert Decimal(str(db.scalar("SELECT opweightb FROM items WHERE code='IT1'"))) == Decimal("90")


def test_initopstock_resets_items():
    db = make_db(); _seed(db)
    with db._engine.begin() as c:
        c.execute(text("INSERT INTO items VALUES ('IT9',5,5,9,9,1,1,0)"))
    YearEndCloseService(db).close_accounts(DATE, {"initopstock": True})
    assert Decimal(str(db.scalar("SELECT opqtyb FROM items WHERE code='IT9'"))) == Decimal("0")
    assert Decimal(str(db.scalar("SELECT opweight FROM items WHERE code='IT9'"))) == Decimal("0")


def test_validations():
    db = make_db()
    with pytest.raises(YearEndCloseError):
        YearEndCloseService(db).close_accounts("", {"chsales": True})
