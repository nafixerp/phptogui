"""Marked List — port of MarkedListController::data.

Sold item lines (``salesd`` + ``salesm``) filtered by salesman, item type
(G/S/O or ornament Y/N), and the ``mark`` flag. Computes gross weight
(weight - stonewgt) and total smith making charge from the barcode smith rate.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, weight as wq

_ZERO = Decimal("0")


class MarkedListService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = int(rlevel or 1)

    def _col(self, t: str, c: str) -> bool:
        return self.db.table_exists(t) and self.db.column_exists(t, c)

    def report(self, date1: str, date2: str, smcode: str = "", itemcode: str = "",
               type_: str = "", marked: str = "") -> list[dict]:
        if not self.db.table_exists("salesm") or not self.db.table_exists("salesd"):
            return []
        itemname = "i.name" if self._col("items", "name") else "''"
        smithmc = ("(SELECT bc.smithmcrate FROM barcode bc WHERE bc.bcode=d.bcode LIMIT 1)"
                   if self._col("barcode", "smithmcrate") else "0")
        where = ["m.tdate BETWEEN :f AND :t"]
        params: dict = {"f": date1, "t": date2}
        if self._col("salesm", "control"):
            where.append("m.control <= :g"); params["g"] = self.rlevel
        if smcode.strip() and self._col("salesm", "smcode"):
            where.append("m.smcode = :sm"); params["sm"] = smcode.strip()
        if itemcode.strip():
            where.append("i.code = :ic"); params["ic"] = itemcode.strip()
        if type_ in ("G", "S", "O") and self._col("items", "itype"):
            where.append("i.itype = :ty"); params["ty"] = type_
        elif type_ == "orn_Y" and self._col("items", "ornament"):
            where.append("i.ornament = 'Y'")
        elif type_ == "orn_N" and self._col("items", "ornament"):
            where.append("i.ornament = 'N'")
        if marked == "Y":
            where.append("d.mark = 'Y'")
        elif marked == "N":
            where.append("(d.mark IS NULL OR d.mark <> 'Y')")
        rows = self.db.fetchall(
            f"SELECT m.slno, m.tdate, m.billno, d.qty, d.weight, d.amount, d.stonewgt, "
            f"d.mark, d.rmno, d.name AS dname, d.bcode, {itemname} AS itemname, "
            f"{smithmc} AS smithmc "
            "FROM salesd d JOIN salesm m ON m.slno=d.slno LEFT JOIN items i ON i.code=d.code "
            f"WHERE {' AND '.join(where)} ORDER BY m.tdate, m.slno LIMIT 5000", params)
        out = []
        for r in rows:
            w = wq(r.get("weight")); stw = wq(r.get("stonewgt"))
            smc = money(r.get("smithmc"))
            dname = str(r.get("dname") or "").strip()
            gross = wq(w - stw)
            out.append({
                "slno": r.get("slno"), "tdate": str(r.get("tdate") or ""),
                "billno": str(r.get("billno") or ""), "qty": int(r.get("qty") or 0),
                "weight": w, "stonewgt": stw, "grosswgt": gross,
                "amount": money(r.get("amount")), "mark": str(r.get("mark") or ""),
                "rmno": str(r.get("rmno") or "").strip(),
                "displayname": dname if dname else str(r.get("itemname") or "").strip(),
                "tsmithmc": money(gross * smc),
            })
        return out
