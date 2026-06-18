"""Tally Export — port of TallyExportController (daybook -> Tally XML).

Builds a Tally "Import Data" ENVELOPE of vouchers from daybook+daybookpart in a
date range (control <= gilevel). Each daybook row becomes a two-ledger voucher
(debit account name / opposite account name); voucher type is guessed from the
vchno prefix (VR=Receipt, VP=Payment, JL=Journal).
"""

from __future__ import annotations

from datetime import datetime
from xml.sax.saxutils import escape

from ...core.db import Database


def _vtype(vchno: str) -> str:
    p = (vchno or "").strip().upper()[:2]
    return {"VR": "Receipt", "VP": "Payment", "JL": "Journal"}.get(p, "Journal")


def _fmt_date(raw) -> str:
    s = str(raw or "")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt) - 2 if "%H" not in fmt else len(s)], "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        return datetime.today().strftime("%Y%m%d")


class TallyExportService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = int(gilevel or 1)

    def fetch_vouchers(self, date_from: str, date_to: str) -> list[dict]:
        if not self.db.table_exists("daybook") or not self.db.table_exists("daybookpart"):
            return []
        return self.db.fetchall(
            "SELECT d.slno, d.tdate, TRIM(COALESCE(p.vchno,'')) AS vchno, "
            "TRIM(COALESCE(p.particular,'')) AS particular, d.amount, "
            "TRIM(COALESCE(a.name, d.accode, '')) AS debit_ac, "
            "TRIM(COALESCE(oa.name, d.opaccode, '')) AS credit_ac "
            "FROM daybook d JOIN daybookpart p ON p.slno = d.slno "
            "LEFT JOIN accountm a ON TRIM(d.accode) = TRIM(a.accode) "
            "LEFT JOIN accountm oa ON TRIM(d.opaccode) = TRIM(oa.accode) "
            "WHERE d.tdate BETWEEN :f AND :t AND d.control <= :g ORDER BY d.tdate, d.slno",
            {"f": date_from, "t": date_to, "g": self.gilevel},
        )

    def _voucher_xml(self, v: dict) -> str:
        date = _fmt_date(v.get("tdate"))
        vchno = escape(str(v.get("vchno") or ""))
        narration = escape(str(v.get("particular") or ""))
        debit_ac = escape(str(v.get("debit_ac") or "Cash"))
        credit_ac = escape(str(v.get("credit_ac") or "Cash"))
        amount = f"{abs(float(v.get('amount') or 0)):.2f}"
        vtype = _vtype(str(v.get("vchno") or ""))
        return (
            '    <TALLYMESSAGE xmlns:UDF="TallyUDF">\n'
            f'      <VOUCHER REMOTEID="GOLDAPP-{vchno}" VCHTYPE="{vtype}" ACTION="Create">\n'
            f"        <DATE>{date}</DATE>\n"
            f"        <VOUCHERNUMBER>{vchno}</VOUCHERNUMBER>\n"
            f"        <NARRATION>{narration}</NARRATION>\n"
            f"        <VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>\n"
            "        <ALLLEDGERENTRIES.LIST>\n"
            f"          <LEDGERNAME>{debit_ac}</LEDGERNAME>\n"
            "          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>\n"
            f"          <AMOUNT>-{amount}</AMOUNT>\n"
            "        </ALLLEDGERENTRIES.LIST>\n"
            "        <ALLLEDGERENTRIES.LIST>\n"
            f"          <LEDGERNAME>{credit_ac}</LEDGERNAME>\n"
            "          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>\n"
            f"          <AMOUNT>{amount}</AMOUNT>\n"
            "        </ALLLEDGERENTRIES.LIST>\n"
            "      </VOUCHER>\n"
            "    </TALLYMESSAGE>\n"
        )

    def export_xml(self, date_from: str, date_to: str) -> str:
        vouchers = self.fetch_vouchers(date_from, date_to)
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<ENVELOPE>\n'
        xml += '  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>\n'
        xml += ('  <BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME>'
                '<STATICVARIABLES><SVCURRENTCOMPANY>##SVCURRENTCOMPANY</SVCURRENTCOMPANY></STATICVARIABLES>'
                '</REQUESTDESC><REQUESTDATA>\n')
        for v in vouchers:
            xml += self._voucher_xml(v)
        xml += '</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>'
        return xml

    def export_to_file(self, date_from: str, date_to: str, path: str) -> int:
        xml = self.export_xml(date_from, date_to)
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml)
        return len(self.fetch_vouchers(date_from, date_to))
