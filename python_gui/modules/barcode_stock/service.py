"""Barcode stock list + verification (read-only).

Source: BarcodeStockListController / StockVerificationController. Lists in-stock
barcodes (stk='Y') with optional counter/item filters and weight/qty totals, and
looks up a single barcode for verification scanning (returns details + an
in-stock flag).
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, weight


class BarcodeStockService:
    def __init__(self, database: Database):
        self.db = database

    def list_stock(self, counter: str = "", icode: str = "", in_stock_only: bool = True) -> dict:
        if not self.db.table_exists("barcode"):
            return {"rows": [], "total_qty": Decimal("0"), "total_weight": weight(0)}
        where = ["1=1"]
        params: dict = {}
        if in_stock_only:
            where.append("UPPER(TRIM(COALESCE(stk,'Y'))) = 'Y'")
        if counter.strip():
            where.append("UPPER(TRIM(COALESCE(counter,''))) = :ct"); params["ct"] = counter.strip().upper()
        if icode.strip():
            where.append("UPPER(TRIM(COALESCE(icode,''))) = :ic"); params["ic"] = icode.strip().upper()
        rows = self.db.fetchall(
            "SELECT bcode, TRIM(COALESCE(icode,'')) AS icode, COALESCE(qty,0) AS qty, "
            "COALESCE(weight,0) AS weight, TRIM(COALESCE(qtype,'')) AS qtype, "
            "TRIM(COALESCE(counter,'')) AS counter, TRIM(COALESCE(stk,'Y')) AS stk "
            f"FROM barcode WHERE {' AND '.join(where)} ORDER BY bcode DESC LIMIT 2000", params)
        tq = sum((money(r.get("qty")) for r in rows), Decimal("0"))
        tw = sum((weight(r.get("weight")) for r in rows), weight(0))
        return {"rows": rows, "total_qty": money(tq), "total_weight": weight(tw)}

    def lookup(self, bcode: int) -> dict | None:
        if not self.db.table_exists("barcode"):
            return None
        row = self.db.fetchone("SELECT * FROM barcode WHERE bcode = :b LIMIT 1", {"b": bcode})
        if not row:
            return None
        stk = str(row.get("stk") or "N").strip().upper()
        itemname = ""
        if self.db.table_exists("items"):
            itemname = str(self.db.scalar(
                "SELECT name FROM items WHERE UPPER(TRIM(code)) = :c LIMIT 1",
                {"c": str(row.get("icode") or "").strip().upper()}) or "")
        return {
            "bcode": row.get("bcode"), "icode": str(row.get("icode") or "").strip(),
            "itemname": itemname, "weight": str(row.get("weight") or 0),
            "qtype": str(row.get("qtype") or "").strip(), "counter": str(row.get("counter") or "").strip(),
            "stk": stk, "in_stock": stk == "Y", "out_of_stock": stk == "N",
        }
