"""Counter Issue — port of CounterIssueController::data / lookupBarcode.

Lists the barcoded stock currently sitting on a counter (``barcode.counter``),
with item names and net weight (weight - stone weight). Read-only view of what
is issued to each counter.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, weight as wq


class CounterIssueService:
    def __init__(self, database: Database):
        self.db = database

    def counters(self) -> list[dict]:
        if not self.db.table_exists("counter"):
            return []
        return self.db.fetchall(
            "SELECT TRIM(code) AS code, TRIM(COALESCE(name,'')) AS name FROM counter ORDER BY code")

    def by_counter(self, counter: str) -> dict:
        if not self.db.table_exists("barcode"):
            return {"rows": [], "counterName": ""}
        itemname = "items.name" if self.db.table_exists("items") else "''"
        rows = self.db.fetchall(
            f"SELECT barcode.bcode, barcode.icode, barcode.qty, barcode.weight, "
            f"barcode.stweight, barcode.dmdwgt, barcode.tdate, barcode.stk, "
            f"barcode.rate, barcode.cost, {itemname} AS itemname "
            "FROM barcode LEFT JOIN items ON barcode.icode = items.code "
            "WHERE barcode.counter = :c ORDER BY barcode.bcode LIMIT 5000",
            {"c": counter})
        out = []
        for r in rows:
            w = wq(r.get("weight")); stw = wq(r.get("stweight"))
            out.append({
                "bcode": int(r.get("bcode") or 0), "icode": str(r.get("icode") or "").strip(),
                "itemname": str(r.get("itemname") or "").strip(), "qty": int(r.get("qty") or 0),
                "weight": w, "stweight": stw, "netwgt": wq(w - stw),
                "dmdwgt": wq(r.get("dmdwgt")), "tdate": str(r.get("tdate") or ""),
                "stk": str(r.get("stk") or "").strip(), "rate": money(r.get("rate")),
                "cost": money(r.get("cost")),
            })
        cname = ""
        if counter and self.db.table_exists("counter"):
            cname = str(self.db.scalar(
                "SELECT name FROM counter WHERE code = :c", {"c": counter}) or "").strip()
        return {"rows": out, "counterName": cname}
