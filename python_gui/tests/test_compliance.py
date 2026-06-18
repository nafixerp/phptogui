"""Tally XML export + GST summary from daybook."""

from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.gst_report.service import GstSummaryService
from python_gui.modules.tally_export.service import TallyExportService, _vtype


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE daybook (slno INT, tdate TEXT, accode TEXT, amount NUM, control INT, opaccode TEXT)"))
        c.execute(text("CREATE TABLE daybookpart (slno INT, vchno TEXT, particular TEXT)"))
        c.execute(text("CREATE TABLE accountm (accode TEXT, name TEXT)"))
        c.execute(text("INSERT INTO accountm VALUES ('CASH','Cash'),('C0001','ACME'),('RS','Sales'),('SGST','SGST Payable'),('CGST','CGST Payable')"))
        # a receipt voucher: customer +1000 / cash -1000
        c.execute(text("INSERT INTO daybookpart VALUES (1,'VRB/00001','By Receipt')"))
        c.execute(text("INSERT INTO daybook VALUES (1,'2026-06-10','C0001',1000,1,'CASH')"))
        c.execute(text("INSERT INTO daybook VALUES (1,'2026-06-10','CASH',-1000,1,'C0001')"))
        # a sale with tax heads
        c.execute(text("INSERT INTO daybookpart VALUES (2,'GST/1','By Sales')"))
        c.execute(text("INSERT INTO daybook VALUES (2,'2026-06-11','RS',10000,1,'C0001')"))
        c.execute(text("INSERT INTO daybook VALUES (2,'2026-06-11','SGST',250,1,'C0001')"))
        c.execute(text("INSERT INTO daybook VALUES (2,'2026-06-11','CGST',250,1,'C0001')"))
    db.table_exists = lambda t: t in ("daybook", "daybookpart", "accountm")
    return db


def test_vtype_guess():
    assert _vtype("VRB/00001") == "Receipt"
    assert _vtype("VPB/00001") == "Payment"
    assert _vtype("JLB/00001") == "Journal"
    assert _vtype("GST/1") == "Journal"


def test_tally_export_builds_vouchers():
    db = make_db()
    xml = TallyExportService(db).export_xml("2026-06-01", "2026-06-30")
    assert xml.startswith('<?xml version="1.0"')
    assert "<ENVELOPE>" in xml and "</ENVELOPE>" in xml
    assert 'VCHTYPE="Receipt"' in xml          # VRB/ -> Receipt
    assert "<VOUCHERNUMBER>VRB/00001</VOUCHERNUMBER>" in xml
    assert xml.count("<TALLYMESSAGE") == 5     # one per daybook row in range


def test_tally_export_to_file(tmp_path):
    db = make_db()
    path = tmp_path / "tally.xml"
    n = TallyExportService(db).export_to_file("2026-06-01", "2026-06-30", str(path))
    assert n == 5 and path.read_text().startswith('<?xml')


def test_gst_summary_from_daybook_heads():
    db = make_db()
    s = GstSummaryService(db).summary("2026-06-01", "2026-06-30")
    assert s["sgst"] == Decimal("250.00")
    assert s["cgst"] == Decimal("250.00")
    assert s["igst"] == Decimal("0.00")
    assert s["total_tax"] == Decimal("500.00")
    assert s["taxable"] == Decimal("10000.00")
