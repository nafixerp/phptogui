"""Phase 10: e-invoice register, outstanding tax, TDS report, purity certificate."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.einvoice_register.service import EInvoiceRegisterService
from python_gui.modules.outstanding_tax.service import OutstandingTaxService
from python_gui.modules.purity_certificate.service import PurityCertificateService
from python_gui.modules.tds_report.service import TdsReportService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    tabs = set(colmap)
    db.table_exists = lambda t: t in tabs
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


# ── e-invoice register ───────────────────────────────────────────────────────

def make_einv_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE e_invoices (id INT, bill_no TEXT, bill_date TEXT, customer_code TEXT, customer_name TEXT, "
                       "gst_no TEXT, net_total NUM, status TEXT, irn TEXT, ack_no TEXT, ack_date TEXT, generated_at TEXT, cancelled_at TEXT)"))
        c.execute(text("INSERT INTO e_invoices VALUES (1,'S1','2026-06-10','C1','ACME','29ABC','10300','generated','IRN1','A1','2026-06-10','2026-06-10 10:00',NULL)"))
        c.execute(text("INSERT INTO e_invoices VALUES (2,'S2','2026-06-12','C2','BETA','29DEF','5150','cancelled','IRN2','A2','2026-06-12','2026-06-12 11:00','2026-06-13 09:00')"))
    _bind(db, {"e_invoices": {"id", "bill_no", "bill_date", "customer_code", "customer_name", "gst_no", "net_total", "status", "irn", "ack_no", "ack_date", "generated_at", "cancelled_at"}})
    return db


def test_einvoice_register_filter():
    svc = EInvoiceRegisterService(make_einv_db())
    allrows = svc.register("2026-06-01", "2026-06-30")
    assert len(allrows) == 2
    assert {r["bill_no"]: r["net_total"] for r in allrows}["S1"] == Decimal("10300.00")
    gen = svc.register("2026-06-01", "2026-06-30", status="generated")
    assert {r["bill_no"] for r in gen} == {"S1"}
    assert svc.details("S1")["irn"] == "IRN1"


# ── outstanding tax ──────────────────────────────────────────────────────────

def make_tax_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE salesm (tdate TEXT, control INT, sgst NUM, cgst NUM, igst NUM, staxamt NUM, tcsamt NUM)"))
        c.execute(text("CREATE TABLE purchasem (tdate TEXT, control INT, sgst NUM, cgst NUM, igst NUM, tcsamt NUM)"))
        c.execute(text("INSERT INTO salesm VALUES ('2026-06-10',1,150,150,0,300,50)"))
        c.execute(text("INSERT INTO purchasem VALUES ('2026-06-12',1,100,100,0,0)"))
    _bind(db, {"salesm": {"tdate", "control", "sgst", "cgst", "igst", "staxamt", "tcsamt"},
               "purchasem": {"tdate", "control", "sgst", "cgst", "igst", "tcsamt"}})
    return db


def test_outstanding_tax_net():
    res = OutstandingTaxService(make_tax_db()).report("2026-06-01", "2026-06-30")
    # output = 150+150 SGST/CGST + 50 TCS = 350 ; input = 100+100 = 200 ; net = 150 payable
    assert res["total_output"] == Decimal("350.00")
    assert res["total_input"] == Decimal("200.00")
    assert res["net"] == Decimal("150.00") and res["net_label"] == "Payable"
    descs = {r["description"] for r in res["rows"]}
    assert "Sales - SGST" in descs and "Purchase - CGST" in descs and "Sales - TCS" in descs


# ── TDS report ───────────────────────────────────────────────────────────────

def make_tds_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE smithm (slno INT, tdate TEXT, docno TEXT, smithcode TEXT, tmcharge NUM, tdsperc NUM, tdsamt NUM, control INT)"))
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, ctype TEXT)"))
        c.execute(text("INSERT INTO smithm VALUES (1,'2026-06-10','D1','SM1',10000,5,500,1)"))
        c.execute(text("INSERT INTO smithm VALUES (2,'2026-06-12','D2','SM2',0,0,0,1)"))  # no TDS -> excluded
        c.execute(text("INSERT INTO clients VALUES ('SM1','Smith One','J')"))
    _bind(db, {"smithm": {"slno", "tdate", "docno", "smithcode", "tmcharge", "tdsperc", "tdsamt", "control"},
               "clients": {"code", "name", "ctype"}})
    return db


def test_tds_report():
    res = TdsReportService(make_tds_db()).report("2026-06-01", "2026-06-30")
    assert len(res["rows"]) == 1
    assert res["rows"][0]["name"] == "Smith One"
    assert res["totals"]["tdsamt"] == Decimal("500.00")


# ── purity certificate ───────────────────────────────────────────────────────

def make_purity_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE generali (code TEXT, cvalue INT)"))
        c.execute(text("CREATE TABLE items (code TEXT, name TEXT)"))
        c.execute(text("INSERT INTO generali VALUES ('PURITYCERTNO',4)"))
        c.execute(text("INSERT INTO items VALUES ('R1','Gold Ring')"))
    _bind(db, {"generali": {"code", "cvalue"}, "items": {"code", "name"}})
    return db


def test_purity_certificate_counter_and_search():
    db = make_purity_db(); svc = PurityCertificateService(db)
    assert svc.next_cert_no() == 5  # 4 + 1
    assert svc.increment() == 6  # counter -> 5, preview 5+1
    assert svc.search_items("ring")[0]["code"] == "R1"
