"""PDC (post-dated cheque) Report — port of PdcReportController.

Read register over ``pdclist`` (control <= gilevel) joined to ``accountm`` for
bank and party names. Filter by entry-date or cheque-date range, receipt/payment
(``rp``), pending flag (``pend``), party code and cheque no. Splits each row into
receipt / payment columns. A pending cheque can be removed (``delete``).
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import money


class PdcReportService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = max(1, int(gilevel or 1))

    def report(self, date1: str, date2: str, use_cheque_date: bool = False,
               rp: str = "", pend: str = "", party: str = "", chqno: str = "") -> list[dict]:
        if not self.db.table_exists("pdclist"):
            return []
        has_acc = self.db.table_exists("accountm")
        bankname = ("TRIM(COALESCE(bankm.name,''))" if has_acc else "''")
        partyname = ("TRIM(COALESCE(partym.name,''))" if has_acc else "''")
        joins = ""
        if has_acc:
            joins = ("LEFT JOIN accountm bankm ON TRIM(pdclist.bank) = TRIM(bankm.accode) "
                     "LEFT JOIN accountm partym ON TRIM(pdclist.code) = TRIM(partym.accode)")
        datecol = "pdclist.chqdate" if use_cheque_date else "pdclist.tdate"
        where = ["pdclist.control <= :g", f"{datecol} BETWEEN :f AND :t"]
        params: dict = {"g": self.gilevel, "f": date1, "t": date2}
        if rp in ("R", "P"):
            where.append("pdclist.rp = :rp"); params["rp"] = rp
        if pend in ("P", "N"):
            where.append("pdclist.pend = :pn"); params["pn"] = pend
        if party.strip():
            where.append("TRIM(pdclist.code) = :pc"); params["pc"] = party.strip()
        if chqno.strip():
            where.append("TRIM(pdclist.chqno) = :cn"); params["cn"] = chqno.strip()
        rows = self.db.fetchall(
            "SELECT pdclist.slno, pdclist.tdate, pdclist.docno, pdclist.chqdate, "
            "TRIM(COALESCE(pdclist.bank,'')) AS bank, TRIM(COALESCE(pdclist.code,'')) AS code, "
            "TRIM(COALESCE(pdclist.chqno,'')) AS chqno, COALESCE(pdclist.amount,0) AS amount, "
            "TRIM(COALESCE(pdclist.particulars,'')) AS particulars, "
            "TRIM(COALESCE(pdclist.rp,'')) AS rp, TRIM(COALESCE(pdclist.pend,'')) AS pend, "
            f"{bankname} AS bankname, {partyname} AS partyname "
            f"FROM pdclist {joins} WHERE {' AND '.join(where)} "
            "ORDER BY pdclist.tdate, pdclist.docno LIMIT 5000", params)
        out = []
        for r in rows:
            amt = money(r.get("amount"))
            rpv = str(r.get("rp") or "")
            out.append({
                "slno": int(r.get("slno") or 0), "tdate": str(r.get("tdate") or ""),
                "docno": str(r.get("docno") or ""), "chqdate": str(r.get("chqdate") or ""),
                "bank": str(r.get("bank") or ""), "code": str(r.get("code") or ""),
                "chqno": str(r.get("chqno") or ""), "amount": amt,
                "particulars": str(r.get("particulars") or ""), "rp": rpv,
                "pend": str(r.get("pend") or ""), "bankname": str(r.get("bankname") or ""),
                "partyname": str(r.get("partyname") or ""),
                "receipt": amt if rpv == "R" else money(0),
                "payment": amt if rpv == "P" else money(0),
            })
        return out

    def delete(self, slno: int) -> str:
        if self.db.table_exists("pdclist"):
            self.db.execute("DELETE FROM pdclist WHERE slno = :s", {"s": int(slno)})
        return "Cheque removed"
