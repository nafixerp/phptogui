"""Bucket C prints: GST split, totals gathering, passbook continuation cursor."""

import os
import sqlite3
import tempfile
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core import printing
from python_gui.core.db import Database
from python_gui.modules.passbook_print.service import PassbookPrintError, PassbookPrintService
from python_gui.modules.purchase_bill_print.service import PurchaseBillPrintService
from python_gui.modules.sales_bill_print.service import SalesBillPrintError, SalesBillPrintService
from python_gui.modules.sales_return_print.service import SalesReturnPrintService

sqlite3.register_adapter(Decimal, str)

try:
    import reportlab  # noqa: F401
    HAVE_RL = True
except Exception:
    HAVE_RL = False


def _bind(db, colmap):
    db.table_exists = lambda t: t in colmap
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


# ---- gst_split (pure business rule) --------------------------------------

def test_gst_split_intrastate_from_amount():
    # only the amount stored -> reconstruct rate from base, split half/half
    g = printing.gst_split(Decimal("300"), 0, "N", base_amt=Decimal("10000"))
    assert not g["is_igst"]
    assert g["cgst"] == Decimal("150.00") and g["sgst"] == Decimal("150.00")
    assert g["eff_perc"] == Decimal("3.000")
    assert g["cgst_label"] == "CGST (1.5%)"


def test_gst_split_interstate():
    g = printing.gst_split(Decimal("500"), 5, "Y", base_amt=Decimal("10000"))
    assert g["is_igst"]
    assert g["igst"] == Decimal("500.00") and g["cgst"] == Decimal("0.00")
    assert g["igst_label"] == "IGST (5.0%)"


def test_gst_split_zero():
    g = printing.gst_split(0, 0, "N", base_amt=0, net_amt=0)
    assert g["cgst"] == Decimal("0.00") and g["igst"] == Decimal("0.00")


# ---- sales bill print -----------------------------------------------------

_SALES = {
    "salesm": {"slno", "billno", "tdate", "custcode", "custname", "smcode", "statecode",
               "billamt", "netamt", "staxamt", "staxperc", "discount", "round", "ramt", "cst", "control"},
    "salesd": {"slno", "sno", "code", "name", "qty", "weight", "stonewgt", "rate", "mcharge", "amount"},
    "items": {"code", "name"}, "clients": {"code", "name", "addr1", "addr2"},
    "sman": {"code", "name"}, "state": {"code", "name"}, "generals": {"code", "cvalue"},
}


def make_sales_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE salesm (slno INT, billno TEXT, tdate TEXT, custcode TEXT, custname TEXT, smcode TEXT, statecode TEXT, billamt NUM, netamt NUM, staxamt NUM, staxperc NUM, discount NUM, round NUM, ramt NUM, cst TEXT, control INT)"))
        c.execute(text("CREATE TABLE salesd (slno INT, sno INT, code TEXT, name TEXT, qty INT, weight NUM, stonewgt NUM, rate NUM, mcharge NUM, amount NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, addr1 TEXT, addr2 TEXT)"))
        c.execute(text("CREATE TABLE sman (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE state (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE generals (code TEXT, cvalue TEXT)"))
        c.execute(text("INSERT INTO salesm VALUES (5,'B100','2024-05-01','C1','ACME','S1','29',10000,10300,300,0,0,0,5000,'N',1)"))
        c.execute(text("INSERT INTO salesd VALUES (5,1,'IT1','',2,10,1,5000,200,6000)"))
        c.execute(text("INSERT INTO salesd VALUES (5,2,'IT2','Ring',1,5,0.5,5000,100,4000)"))
        c.execute(text("INSERT INTO items VALUES ('IT1','Bangle')"))
        c.execute(text("INSERT INTO clients VALUES ('C1','ACME Jewels','12 Main St','City')"))
        c.execute(text("INSERT INTO sman VALUES ('S1','Ravi')"))
        c.execute(text("INSERT INTO generals VALUES ('SHOPNM','Gold Palace')"))
        c.execute(text("INSERT INTO generals VALUES ('SHOPADDR','MG Road')"))
    _bind(db, _SALES)
    return db


def test_sales_bill_gather():
    svc = SalesBillPrintService(make_sales_db())
    d = svc.gather(5)
    assert d["billno"] == "B100" and d["salesman"] == "Ravi"
    assert d["company"]["name"] == "Gold Palace"
    assert d["customer_address"] == "12 Main St, City"
    # blank detail name falls back to items.name; missing item keeps blank
    assert d["rows"][0]["name"] == "Bangle"
    assert d["rows"][1]["name"] == "Ring"
    # net weight = weight - stonewgt
    assert d["rows"][0]["netwgt"] == Decimal("9.000")
    # totals
    assert d["row_totals"]["amount"] == Decimal("10000")
    assert d["row_totals"]["qty"] == Decimal("3")
    # gst split from staxamt 300 on base 10000 -> 1.5% each, 150/150
    assert d["gst"]["cgst"] == Decimal("150.00") and d["gst"]["sgst"] == Decimal("150.00")
    assert d["title"] == "Tax Invoice"


def test_sales_bill_not_found():
    with pytest.raises(SalesBillPrintError):
        SalesBillPrintService(make_sales_db()).gather(999)


@pytest.mark.skipif(not HAVE_RL, reason="reportlab not installed")
def test_sales_bill_render_pdf():
    svc = SalesBillPrintService(make_sales_db())
    path = os.path.join(tempfile.gettempdir(), "test_sales_bill.pdf")
    out = svc.render_pdf(5, path)
    assert os.path.exists(out) and os.path.getsize(out) > 0
    os.remove(out)


# ---- sales return print ---------------------------------------------------

_SRET = {
    "salesrm": {"slno", "billno", "tdate", "custcode", "custname", "sr", "billamt", "netamt",
                "pamt", "staxamt", "staxperc", "discount", "ob", "cst", "control", "sbillno"},
    "salesrd": {"slno", "sno", "code", "name", "qty", "weight", "stonewgt", "rate", "amount"},
    "items": {"code", "name"}, "clients": {"code", "name", "addr1"},
}


def make_sret_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE salesrm (slno INT, billno TEXT, tdate TEXT, custcode TEXT, custname TEXT, sr TEXT, billamt NUM, netamt NUM, pamt NUM, staxamt NUM, staxperc NUM, discount NUM, ob NUM, cst TEXT, control INT, sbillno TEXT)"))
        c.execute(text("CREATE TABLE salesrd (slno INT, sno INT, code TEXT, name TEXT, qty INT, weight NUM, stonewgt NUM, rate NUM, amount NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, addr1 TEXT)"))
        c.execute(text("INSERT INTO salesrm VALUES (3,'R55','2024-06-01','C1','ACME','R',5000,5000,2000,0,0,0,1000,'N',1,'B100')"))
        c.execute(text("INSERT INTO salesrd VALUES (3,1,'IT1','Chain',1,8,1,5000,5000)"))
        c.execute(text("INSERT INTO items VALUES ('IT1','Chain')"))
        c.execute(text("INSERT INTO clients VALUES ('C1','ACME','Road')"))
    _bind(db, _SRET)
    return db


def test_sales_return_gather_by_billno():
    svc = SalesReturnPrintService(make_sret_db())
    d = svc.gather(billno="R55")
    assert d["billno"] == "R55"
    assert d["rows"][0]["netwgt"] == Decimal("7.000")
    # refund = netamt - pamt = 5000 - 2000 = 3000 ; closing = ob + refund = 4000
    assert d["refund"] == Decimal("3000.00")
    assert d["closing_balance"] == Decimal("4000.00")
    assert d["title"] == "Sales Return Invoice"


# ---- purchase bill print --------------------------------------------------

_PUR = {
    "purchasem": {"slno", "docno", "tdate", "suppcode", "suppname", "pr", "netamt", "taxamt",
                  "cgst", "sgst", "igst", "cst", "pamt", "bal"},
    "purchased": {"slno", "sno", "code", "name", "iqtype", "qty", "weight", "stwgt", "lesswgt", "mud", "netwgt", "rate", "mcharge", "amount"},
    "items": {"code", "name"}, "clients": {"code", "name", "addr1"},
}


def make_pur_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE purchasem (slno INT, docno TEXT, tdate TEXT, suppcode TEXT, suppname TEXT, pr TEXT, netamt NUM, taxamt NUM, cgst NUM, sgst NUM, igst NUM, cst TEXT, pamt NUM, bal NUM)"))
        c.execute(text("CREATE TABLE purchased (slno INT, sno INT, code TEXT, name TEXT, iqtype TEXT, qty INT, weight NUM, stwgt NUM, lesswgt NUM, mud NUM, netwgt NUM, rate NUM, mcharge NUM, amount NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, addr1 TEXT)"))
        # taxamt 200, no cgst/sgst stored, cst N -> reconstruct 100/100
        c.execute(text("INSERT INTO purchasem VALUES (7,'P9','2024-07-01','SUP1','Supplier','P',10200,200,0,0,0,'N',5000,5200)"))
        c.execute(text("INSERT INTO purchased VALUES (7,1,'IT1','Gold Bar','22K',1,100,0,0,0,NULL,5000,0,10000)"))
        c.execute(text("INSERT INTO items VALUES ('IT1','Gold Bar')"))
        c.execute(text("INSERT INTO clients VALUES ('SUP1','Supplier','Lane')"))
    _bind(db, _PUR)
    return db


def test_purchase_bill_gather_reconstructs_gst():
    svc = PurchaseBillPrintService(make_pur_db())
    d = svc.gather(slno=7)
    assert d["docno"] == "P9"
    # netwgt computed = 100 - 0 - 0 - 0 = 100
    assert d["rows"][0]["netwgt"] == Decimal("100.000")
    # taxamt 200, cst N -> cgst/sgst 100/100
    assert d["cgst"] == Decimal("100.00") and d["sgst"] == Decimal("100.00")
    assert d["balance"] == Decimal("5200.00")


# ---- passbook print (stateful continuation cursor) ------------------------

_PB = {
    "clients": {"code", "name", "addr1", "addr2", "addr3", "lpslno", "lpline", "lpsno"},
    "kuricolln": {"slno", "code", "tdate", "docno", "rcptno", "amount", "grate", "wgt", "agent"},
}


def make_pb_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, addr1 TEXT, addr2 TEXT, addr3 TEXT, lpslno INT, lpline INT, lpsno INT)"))
        c.execute(text("CREATE TABLE kuricolln (slno INT, code TEXT, tdate TEXT, docno TEXT, rcptno TEXT, amount NUM, grate NUM, wgt NUM, agent TEXT)"))
        c.execute(text("INSERT INTO clients VALUES ('K1','Member','A1','A2','',0,0,0)"))
        c.execute(text("INSERT INTO kuricolln VALUES (1,'K1','2024-01-01','D1','R1',1000,5000,0.2,'AG')"))
        c.execute(text("INSERT INTO kuricolln VALUES (2,'K1','2024-02-01','D2','R2',1000,5100,0.196,'AG')"))
        c.execute(text("INSERT INTO kuricolln VALUES (3,'K1','2024-03-01','D3','R3',1000,5200,0.192,'AG')"))
    _bind(db, _PB)
    return db


def test_passbook_build_advances_cursor():
    db = make_pb_db()
    res = PassbookPrintService(db).build("k1")
    printed = [r for r in res["rows"] if not r.get("blank")]
    assert len(printed) == 3
    assert printed[0]["amount"] == Decimal("1000.00") and printed[0]["wgt"] == Decimal("0.200")
    # cursor advanced to last slno=3, passbook no = start(1)+3-1 = 3
    assert res["summary"]["last_slno"] == 3
    assert res["summary"]["last_passbook_no"] == 3
    assert int(db.scalar("SELECT lpslno FROM clients WHERE code='K1'")) == 3
    assert int(db.scalar("SELECT lpsno FROM clients WHERE code='K1'")) == 3


def test_passbook_continuation_only_new_rows():
    db = make_pb_db()
    svc = PassbookPrintService(db)
    svc.build("K1")  # prints all 3, cursor -> slno 3
    # add a new collection and re-run: only the new row prints (slno > lpslno)
    with db._engine.begin() as c:
        c.execute(text("INSERT INTO kuricolln VALUES (4,'K1','2024-04-01','D4','R4',1000,5300,0.188,'AG')"))
    res = svc.build("K1")
    printed = [r for r in res["rows"] if not r.get("blank")]
    assert len(printed) == 1 and printed[0]["slno"] == 4


def test_passbook_reset_prints_all():
    db = make_pb_db()
    svc = PassbookPrintService(db)
    svc.build("K1")
    res = svc.build("K1", reset=True)
    printed = [r for r in res["rows"] if not r.get("blank")]
    assert len(printed) == 3


def test_passbook_lookup_and_errors():
    db = make_pb_db()
    svc = PassbookPrintService(db)
    info = svc.party_lookup("K1")
    assert info["start_slno"] == 1 and info["start_docno"] == "D1"
    with pytest.raises(PassbookPrintError):
        svc.party_lookup("NOPE")
    svc.build("K1")
    with pytest.raises(PassbookPrintError):
        svc.build("K1")  # nothing more to print
