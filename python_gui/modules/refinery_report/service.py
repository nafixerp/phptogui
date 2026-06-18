"""Refinery Report — port of RefineryReportController::data.

Read register over ``refinerym`` joined to ``refineryd`` (and item/refiner
names), filtered by date range, optional refiner code, and status
(1 = Forward, 2 = Return). Issued/received weights are Decimal.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, weight as wq


class RefineryReportService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = max(1, int(gilevel or 1))

    def report(self, date1: str, date2: str, refcode: str = "", status: str = "") -> list[dict]:
        if not (self.db.table_exists("refinerym") and self.db.table_exists("refineryd")):
            return []
        join_i = "LEFT JOIN items i ON TRIM(i.code) = TRIM(d.code)" if self.db.table_exists("items") else ""
        iname = "TRIM(COALESCE(i.name, d.code))" if self.db.table_exists("items") else "TRIM(d.code)"
        join_c = "LEFT JOIN clients c ON TRIM(c.code) = TRIM(m.refcode)" if self.db.table_exists("clients") else ""
        rname = "TRIM(COALESCE(c.name, m.refcode))" if self.db.table_exists("clients") else "TRIM(m.refcode)"
        where = ["m.tdate BETWEEN :f AND :t"]
        params: dict = {"f": date1, "t": date2}
        if refcode.strip():
            where.append("UPPER(TRIM(m.refcode)) = :rc"); params["rc"] = refcode.strip().upper()
        if status.strip() in ("1", "2"):
            where.append("m.status = :st"); params["st"] = int(status)
        rows = self.db.fetchall(
            f"SELECT m.tdate, m.docno, COALESCE(m.status,1) AS status, "
            f"{rname} AS refinername, {iname} AS itemname, TRIM(d.code) AS itemcode, "
            "d.issuedwgt, d.issuedqty, d.issuedstwgt, d.rcvdwgt, d.rcvdqty, d.rcvdtouch, "
            "d.touch, d.stktype, d.rate, m.testperc, m.expwgt, m.note, m.charge "
            f"FROM refinerym m JOIN refineryd d ON d.slno = m.slno {join_i} {join_c} "
            f"WHERE {' AND '.join(where)} ORDER BY m.tdate, m.slno, d.sno LIMIT 5000", params)
        out = []
        for r in rows:
            st = int(r.get("status") or 1)
            out.append({
                "tdate": str(r.get("tdate") or ""), "docno": str(r.get("docno") or "").strip(),
                "status": st, "status_lbl": "Return" if st == 2 else "Forward",
                "refinername": str(r.get("refinername") or ""), "itemname": str(r.get("itemname") or ""),
                "itemcode": str(r.get("itemcode") or ""),
                "issuedwgt": wq(r.get("issuedwgt")), "issuedqty": int(r.get("issuedqty") or 0),
                "issuedstwgt": wq(r.get("issuedstwgt")), "rcvdwgt": wq(r.get("rcvdwgt")),
                "rcvdqty": int(r.get("rcvdqty") or 0), "rcvdtouch": money(r.get("rcvdtouch")),
                "touch": money(r.get("touch")), "stktype": str(r.get("stktype") or "").strip(),
                "rate": money(r.get("rate")), "testperc": money(r.get("testperc")),
                "expwgt": wq(r.get("expwgt")), "note": str(r.get("note") or "").strip(),
                "charge": money(r.get("charge")),
            })
        return out
