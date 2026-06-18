"""Phase 8: refinery report + repair complaints master."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.refinery_report.service import RefineryReportService
from python_gui.modules.repair_complaints.service import RepairComplaintsService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


def make_refinery_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE refinerym (slno INT, docno TEXT, tdate TEXT, refcode TEXT, status INT, testperc NUM, expwgt NUM, note TEXT, charge NUM)"))
        c.execute(text("CREATE TABLE refineryd (slno INT, sno INT, code TEXT, issuedwgt NUM, issuedqty INT, issuedstwgt NUM, rcvdwgt NUM, rcvdqty INT, rcvdtouch NUM, touch NUM, stktype TEXT, rate NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT)"))
        c.execute(text("INSERT INTO refinerym VALUES (1,'RF1','2026-06-10','R1',1,91.6,0,'',100)"))
        c.execute(text("INSERT INTO refinerym VALUES (2,'RF2','2026-06-15','R1',2,91.6,0,'',0)"))
        c.execute(text("INSERT INTO refineryd VALUES (1,1,'OG',100.0,1,0,0,0,0,91.6,'R',5000)"))
        c.execute(text("INSERT INTO refineryd VALUES (2,1,'OG',0,0,0,92.0,1,91.6,91.6,'R',5000)"))
        c.execute(text("INSERT INTO items VALUES ('OG','Old Gold')"))
        c.execute(text("INSERT INTO clients VALUES ('R1','Refiner One')"))
    _bind(db, {"refinerym": {"slno", "docno", "tdate", "refcode", "status", "testperc", "expwgt", "note", "charge"},
               "refineryd": {"slno", "sno", "code", "issuedwgt", "issuedqty", "issuedstwgt", "rcvdwgt", "rcvdqty", "rcvdtouch", "touch", "stktype", "rate"},
               "items": {"code", "name"}, "clients": {"code", "name"}})
    return db


def test_refinery_report_all_and_status():
    svc = RefineryReportService(make_refinery_db())
    allrows = svc.report("2026-06-01", "2026-06-30")
    assert len(allrows) == 2
    assert {r["status_lbl"] for r in allrows} == {"Forward", "Return"}
    assert allrows[0]["refinername"] == "Refiner One"
    fwd = svc.report("2026-06-01", "2026-06-30", status="1")
    assert len(fwd) == 1 and fwd[0]["issuedwgt"] == Decimal("100.000")


def make_repcompl_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE repcompl (part TEXT)"))
    _bind(db, {"repcompl": {"part"}})
    return db


def test_repair_complaints_save_dedup_and_delete():
    db = make_repcompl_db(); svc = RepairComplaintsService(db)
    svc.save(["loose stone", "bent ring", "loose stone"])  # dedup -> 2, upper-cased
    assert set(svc.list()) == {"LOOSE STONE", "BENT RING"}
    svc.save(["BENT RING"], deleted=["LOOSE STONE"])
    assert svc.list() == ["BENT RING"]
