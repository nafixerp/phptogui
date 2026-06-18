"""Item Adjustment repository — `itemadj` + items/itemsstk stock movement.

Source: ItemAdjustmentController (save + adjustItemStock). A from->to transfer
records an itemadj row and moves stock: items + itemsstk are incremented by the
signed qty/weight/stone. At control level 1 both primary and `*b` columns move;
otherwise only the `*b` columns (adjustItemStock).
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database, Tx


class ItemAdjustmentRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, t: str) -> bool:
        return self.db.table_exists(t)

    def item_exists(self, code: str) -> bool:
        if not self.db.table_exists("items"):
            return False
        return self.db.fetchone(
            "SELECT 1 FROM items WHERE UPPER(TRIM(code)) = :c LIMIT 1", {"c": code.strip().upper()}
        ) is not None

    def insert_itemadj(self, tx: Tx, row: dict) -> None:
        cols = set(self.db.columns("itemadj"))
        row = {k: v for k, v in row.items() if k.lower() in cols}
        names = ", ".join(row); binds = ", ".join(f":{k}" for k in row)
        tx.execute(f"INSERT INTO itemadj ({names}) VALUES ({binds})", row)

    def adjust_stock(self, tx: Tx, code: str, qty, weight, stonewgt, stktype: str, control: int) -> None:
        code_u = code.strip().upper()
        qty = Decimal(str(qty)); weight = Decimal(str(weight)); stonewgt = Decimal(str(stonewgt))
        # items table
        if self.db.table_exists("items"):
            if control == 1:
                tx.execute(
                    "UPDATE items SET qty = COALESCE(qty,0)+:q, weight = COALESCE(weight,0)+:w, "
                    "qtyb = COALESCE(qtyb,0)+:q, weightb = COALESCE(weightb,0)+:w, "
                    "stonewgt = COALESCE(stonewgt,0)+:s, stonewgtb = COALESCE(stonewgtb,0)+:s "
                    "WHERE UPPER(TRIM(code)) = :c", {"q": qty, "w": weight, "s": stonewgt, "c": code_u})
            else:
                tx.execute(
                    "UPDATE items SET qtyb = COALESCE(qtyb,0)+:q, weightb = COALESCE(weightb,0)+:w, "
                    "stonewgtb = COALESCE(stonewgtb,0)+:s WHERE UPPER(TRIM(code)) = :c",
                    {"q": qty, "w": weight, "s": stonewgt, "c": code_u})
        # itemsstk (by code + stktype)
        if stktype == "" or not self.db.table_exists("itemsstk"):
            return
        exists = tx.scalar("SELECT 1 FROM itemsstk WHERE code = :c AND stktype = :t LIMIT 1",
                           {"c": code_u, "t": stktype}) is not None
        if not exists:
            tx.execute("INSERT INTO itemsstk (code, stktype, qty, weight, stonewgt, qtyb, weightb, stonewgtb) "
                       "VALUES (:c, :t, 0, 0, 0, 0, 0, 0)", {"c": code_u, "t": stktype})
        if control == 1:
            tx.execute(
                "UPDATE itemsstk SET qty = COALESCE(qty,0)+:q, weight = COALESCE(weight,0)+:w, "
                "qtyb = COALESCE(qtyb,0)+:q, weightb = COALESCE(weightb,0)+:w, "
                "stonewgt = COALESCE(stonewgt,0)+:s, stonewgtb = COALESCE(stonewgtb,0)+:s "
                "WHERE code = :c AND stktype = :t", {"q": qty, "w": weight, "s": stonewgt, "c": code_u, "t": stktype})
        else:
            tx.execute(
                "UPDATE itemsstk SET qtyb = COALESCE(qtyb,0)+:q, weightb = COALESCE(weightb,0)+:w, "
                "stonewgtb = COALESCE(stonewgtb,0)+:s WHERE code = :c AND stktype = :t",
                {"q": qty, "w": weight, "s": stonewgt, "c": code_u, "t": stktype})

    def stock_weight(self, code: str, stktype: str = "") -> Decimal:
        if not self.db.table_exists("itemsstk"):
            return Decimal("0")
        sql = "SELECT COALESCE(SUM(weight),0) FROM itemsstk WHERE code = :c"
        params = {"c": code.strip().upper()}
        if stktype:
            sql += " AND stktype = :t"; params["t"] = stktype
        return Decimal(str(self.db.scalar(sql, params) or 0))
