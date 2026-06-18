"""Phase 9: kuri type master, PDC report, smith lot report, gold loan."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.gold_loan.service import GoldLoanService
from python_gui.modules.kuri_type_master.service import KuriTypeMasterService
from python_gui.modules.pdc_report.service import PdcReportService
from python_gui.modules.smith_lot_report.service import SmithLotReportService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


# ── kuri type master ─────────────────────────────────────────────────────────

def make_kuri_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE kuritype (code TEXT, name TEXT, instnos INT, instamt NUM, totamt NUM, "
                       "bonus NUM, colntype TEXT, comnperc NUM, prefix TEXT, lastno INT, collnlimit NUM, collnmin NUM, comnrate NUM)"))
        c.execute(text("CREATE TABLE clients_kuridet (kuritype TEXT)"))
        c.execute(text("INSERT INTO kuritype VALUES ('OLD','Old Scheme',11,1000,11000,500,'M',0,'OS',5,0,0,0)"))
        c.execute(text("INSERT INTO clients_kuridet VALUES ('OLD')"))
    _bind(db, {"kuritype": {"code", "name", "instnos", "instamt", "totamt", "bonus", "colntype", "comnperc", "prefix", "lastno", "collnlimit", "collnmin", "comnrate"},
               "clients_kuridet": {"kuritype"}})
    return db


def test_kuri_type_save_replaces_and_filters():
    db = make_kuri_db(); svc = KuriTypeMasterService(db)
    msg = svc.save([
        {"code": "g1", "name": "Gold 11", "instnos": 11, "instamt": 2000, "totamt": 22000, "bonus": 2000, "colntype": "m"},
        {"code": "", "name": "skip"},  # skipped
    ])
    assert "1" in msg
    rows = {r["code"]: r for r in svc.load()}
    assert set(rows) == {"G1"}  # replaced + upper-cased, OLD gone
    assert rows["G1"]["colntype"] == "M"
    assert Decimal(str(rows["G1"]["totamt"])) == Decimal("22000.00")


def test_kuri_type_in_use():
    assert KuriTypeMasterService(make_kuri_db()).in_use("OLD") is True
    assert KuriTypeMasterService(make_kuri_db()).in_use("ZZZ") is False


# ── PDC report ───────────────────────────────────────────────────────────────

def make_pdc_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE pdclist (slno INT, tdate TEXT, docno TEXT, chqdate TEXT, bank TEXT, code TEXT, "
                       "chqno TEXT, amount NUM, particulars TEXT, rp TEXT, pend TEXT, control INT)"))
        c.execute(text("CREATE TABLE accountm (accode TEXT, name TEXT)"))
        c.execute(text("INSERT INTO pdclist VALUES (1,'2026-06-10','D1','2026-07-10','HDFC','C1','CHQ1',5000,'x','R','P',1)"))
        c.execute(text("INSERT INTO pdclist VALUES (2,'2026-06-12','D2','2026-07-12','HDFC','C2','CHQ2',3000,'y','P','P',1)"))
        c.execute(text("INSERT INTO accountm VALUES ('HDFC','HDFC Bank')"))
        c.execute(text("INSERT INTO accountm VALUES ('C1','Customer One')"))
    _bind(db, {"pdclist": {"slno", "tdate", "docno", "chqdate", "bank", "code", "chqno", "amount", "particulars", "rp", "pend", "control"},
               "accountm": {"accode", "name"}})
    return db


def test_pdc_report_splits_and_filters():
    db = make_pdc_db(); svc = PdcReportService(db)
    rows = svc.report("2026-06-01", "2026-06-30")
    assert len(rows) == 2
    by = {r["slno"]: r for r in rows}
    assert by[1]["receipt"] == Decimal("5000.00") and by[1]["payment"] == Decimal("0.00")
    assert by[1]["bankname"] == "HDFC Bank" and by[1]["partyname"] == "Customer One"
    assert by[2]["payment"] == Decimal("3000.00")
    only_r = svc.report("2026-06-01", "2026-06-30", rp="R")
    assert {r["slno"] for r in only_r} == {1}
    svc.delete(1)
    assert {r["slno"] for r in svc.report("2026-06-01", "2026-06-30")} == {2}


# ── smith lot report ─────────────────────────────────────────────────────────

def make_smith_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE smithm (slno INT, smithcode TEXT, lotno TEXT, control INT, tdate TEXT)"))
        c.execute(text("CREATE TABLE smithd (slno INT, givrec TEXT, netwgt NUM, qty INT)"))
        c.execute(text("INSERT INTO clients VALUES ('S1','Smith One')"))
        c.execute(text("INSERT INTO smithm VALUES (1,'S1','LOT1',1,'2026-06-10')"))
        c.execute(text("INSERT INTO smithm VALUES (2,'S1','LOT1',1,'2026-06-15')"))
        c.execute(text("INSERT INTO smithd VALUES (1,'G',100.0,5)"))  # issued
        c.execute(text("INSERT INTO smithd VALUES (2,'R',60.0,3)"))   # received
    _bind(db, {"clients": {"code", "name"},
               "smithm": {"slno", "smithcode", "lotno", "control", "tdate"},
               "smithd": {"slno", "givrec", "netwgt", "qty"}})
    return db


def test_smith_lot_report_pending():
    rows = SmithLotReportService(make_smith_db()).report("2026-06-01", "2026-06-30")
    assert len(rows) == 1
    r = rows[0]
    assert r["lotno"] == "LOT1"
    assert r["issuewgt"] == Decimal("100.000") and r["rcvdwgt"] == Decimal("60.000")
    assert r["pendwgt"] == Decimal("40.000") and r["pendqty"] == 2


# ── gold loan ────────────────────────────────────────────────────────────────

def make_loan_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE loan (slno INT, docno TEXT, tdate TEXT, billno TEXT, ccode TEXT, cname TEXT, "
                       "loanamt NUM, totalamt NUM, closed TEXT, control INT)"))
        c.execute(text("CREATE TABLE loan_items (slno INT, code TEXT, name TEXT, weight NUM, amount NUM)"))
        c.execute(text("CREATE TABLE loancolln (slno INT, docno TEXT, tdate TEXT, amount NUM)"))
        c.execute(text("INSERT INTO loan VALUES (1,'L1','2026-06-01','B1','C1','ACME',50000,55000,'N',1)"))
        c.execute(text("INSERT INTO loan VALUES (2,'L2','2026-06-05','B2','C2','BETA',20000,22000,'Y',1)"))
        c.execute(text("INSERT INTO loan_items VALUES (1,'OG','Old Gold',25.0,50000)"))
        c.execute(text("INSERT INTO loancolln VALUES (1,'RC1','2026-06-20',10000)"))
    _bind(db, {"loan": {"slno", "docno", "tdate", "billno", "ccode", "cname", "loanamt", "totalamt", "closed", "control"},
               "loan_items": {"slno", "code", "name", "weight", "amount"},
               "loancolln": {"slno", "docno", "tdate", "amount"}})
    return db


def test_gold_loan_list_and_load():
    db = make_loan_db(); svc = GoldLoanService(db)
    assert {r["docno"] for r in svc.list()} == {"L1", "L2"}
    assert {r["docno"] for r in svc.list(only_open=True)} == {"L1"}
    data = svc.load(1)
    assert data is not None
    assert len(data["items"]) == 1 and len(data["collections"]) == 1
    assert data["paid"] == Decimal("10000.00")
    assert data["balance"] == Decimal("45000.00")  # 55000 - 10000
