"""Phase 2/3: model master, party MC table, party op weight, scale,
customer opening bills, party reports."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.core.posting import PostingEngine

sqlite3.register_adapter(Decimal, str)


def dbx(ddl):
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        for s in ddl:
            c.execute(text(s))
    return db


# -- Model Master ------------------------------------------------------------

def test_model_master_bulk_replace_by_type():
    from python_gui.modules.model_master.service import ModelMasterService
    db = dbx(["CREATE TABLE models (mtype TEXT, name TEXT)"])
    db.table_exists = lambda t: t == "models"
    svc = ModelMasterService(db)
    svc.save("M", ["ring", "chain", ""])
    assert [r["name"] for r in svc.list("M")] == ["CHAIN", "RING"]   # upper, ordered by name
    svc.save("M", ["bangle"])                                        # replace
    assert [r["name"] for r in svc.list("M")] == ["BANGLE"]
    svc.save("S", ["sub1"])                                          # different type unaffected
    assert [r["name"] for r in svc.list("M")] == ["BANGLE"]


# -- Party MC Table ----------------------------------------------------------

def test_party_mctable_bulk_replace():
    from python_gui.modules.party_mctable.service import PartyMCTableService
    db = dbx(["CREATE TABLE pmctable (pcode TEXT, icode TEXT, model TEXT, submodel TEXT, wastage NUM, mc NUM, mcperc NUM, mcperqty NUM, touch NUM, formula TEXT)"])
    db.table_exists = lambda t: t == "pmctable"
    svc = PartyMCTableService(db)
    svc.save("P1", [{"icode": "RING", "wastage": "8", "mc": "100"}, {"icode": "", "model": ""}])
    rows = svc.get_for_party("P1")
    assert len(rows) == 1 and rows[0]["icode"] == "RING"
    svc.save("P1", [{"icode": "CHAIN", "mc": "120"}])
    assert [r["icode"] for r in svc.get_for_party("P1")] == ["CHAIN"]


# -- Party Opening Weight ----------------------------------------------------

def test_party_op_weight_update():
    from python_gui.modules.party_op_weight.service import PartyOpWeightError, PartyOpWeightService
    db = dbx(["CREATE TABLE accountm (accode TEXT, name TEXT, opwgt NUM, opwgtb NUM)"])
    with db._engine.begin() as c:
        c.execute(text("INSERT INTO accountm VALUES ('C0001','ACME',0,0)"))
    db.table_exists = lambda t: t == "accountm"
    db.column_exists = lambda t, col: col in ("accode", "name", "opwgt", "opwgtb")
    svc = PartyOpWeightService(db)
    svc.save("C0001", "12.5", "12.5")
    assert Decimal(str(db.scalar("SELECT opwgt FROM accountm WHERE accode='C0001'"))) == Decimal("12.500")
    with pytest.raises(PartyOpWeightError, match="not found"):
        svc.save("GHOST", "1")


# -- Scale -------------------------------------------------------------------

def test_scale_settings_roundtrip():
    from python_gui.modules.scale.service import ScaleService
    db = dbx(["CREATE TABLE generals (code TEXT PRIMARY KEY, cvalue TEXT)"])
    db.table_exists = lambda t: t == "generals"
    svc = ScaleService(db)
    svc.save({"SCALEPORT": "COM3", "SCALEBAUD": "9600"})
    data = svc.load(["SCALEPORT", "SCALEBAUD"])
    assert data["SCALEPORT"] == "COM3" and data["SCALEBAUD"] == "9600"


# -- Customer Opening Bills --------------------------------------------------

def test_customer_op_bills_replace_and_insert():
    from python_gui.modules.customer_op_bills.service import CustomerOpBillsService
    db = dbx([
        "CREATE TABLE salesm (slno INT, billno TEXT, tdate TEXT, custcode TEXT, custname TEXT, billamt NUM, netamt NUM, control INT, status INT)",
        "CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)",
    ])
    cols = {"slno", "billno", "tdate", "custcode", "custname", "billamt", "netamt", "control", "status"}
    db.table_exists = lambda t: t in ("salesm", "generali")
    db.column_exists = lambda t, c: c == "slno"
    db.columns = lambda t: cols if t == "salesm" else set()
    pe = PostingEngine(db); pe.db.table_exists = db.table_exists; pe.db.column_exists = db.column_exists; pe.db.columns = db.columns
    svc = CustomerOpBillsService(pe)
    res = svc.save("C0001", "ACME", [{"billno": "OP001", "billamt": "5000"}, {"billno": "", "billamt": "0"}])
    assert res["saved"] == 1
    bills = svc.bills_for("C0001")
    assert len(bills) == 1 and bills[0]["billno"] == "OP001"
    # re-save replaces (not appends)
    svc.save("C0001", "ACME", [{"billno": "OP002", "billamt": "3000"}])
    assert [b["billno"] for b in svc.bills_for("C0001")] == ["OP002"]


# -- Party Reports -----------------------------------------------------------

def test_party_outstanding_balances():
    from python_gui.modules.party_reports.service import PartyReportsService
    db = dbx([
        "CREATE TABLE clients (code TEXT, name TEXT, ctype TEXT)",
        "CREATE TABLE accountm (accode TEXT, opbal NUM)",
        "CREATE TABLE daybook (accode TEXT, amount NUM, control INT)",
    ])
    with db._engine.begin() as c:
        c.execute(text("INSERT INTO clients VALUES ('C0001','ACME','C')"))
        c.execute(text("INSERT INTO accountm VALUES ('C0001', -1000)"))   # debit opening
        c.execute(text("INSERT INTO daybook VALUES ('C0001', -500, 1)"))  # more debit
    db.table_exists = lambda t: t in ("clients", "accountm", "daybook")
    res = PartyReportsService(db).outstanding("C")
    r = res["rows"][0]
    assert r["balance"] == Decimal("1500.00") and r["side"] == "Dr"
    assert res["total_dr"] == Decimal("1500.00")
