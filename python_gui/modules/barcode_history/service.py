"""Barcode History — port of BarcodeHistoryController.

Assembles the full movement timeline for a single barcode: the *Created* row
(original weight, with transfer adjustments added back), then Sales, Sales
Returns, Smith/Jewl Issue & Receipt, and Transfer Out/In rows. All sources are
table/column guarded and the timeline is sorted by date then doc-no.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, weight as wq

_ZERO = Decimal("0")


class BarcodeHistoryService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = int(gilevel or 1)

    def _has(self, t: str) -> bool:
        return self.db.table_exists(t)

    def _col(self, t: str, c: str) -> bool:
        return self._has(t) and self.db.column_exists(t, c)

    def info(self, bcode: int) -> dict | None:
        if not self._has("barcode"):
            return None
        bc = self.db.fetchone(
            "SELECT icode, qty, rate, weight, stweight, tdate FROM barcode WHERE bcode = :b LIMIT 1",
            {"b": bcode})
        if not bc:
            return None
        name = ""
        if self._has("items"):
            name = str(self.db.scalar(
                "SELECT name FROM items WHERE code = :c", {"c": bc.get("icode")}) or "")
        w = wq(bc.get("weight")); stw = wq(bc.get("stweight"))
        ao, ai = self._adj_sums(bcode)
        return {
            "icode": str(bc.get("icode") or "").strip(), "itemname": name.strip(),
            "qty": int(bc.get("qty") or 0), "rate": money(bc.get("rate")),
            "weight": wq(w + ao[0] - ai[0]), "stweight": wq(stw + ao[1] - ai[1]),
            "tdate": str(bc.get("tdate") or ""),
        }

    def _adj_sums(self, bcode: int):
        """Returns ((out_wgt, out_stwgt), (in_wgt, in_stwgt)) from itemadj."""
        if not self._has("itemadj"):
            return (_ZERO, _ZERO), (_ZERO, _ZERO)
        out = self.db.fetchone(
            "SELECT COALESCE(SUM(fromwgt),0) AS w, COALESCE(SUM(fromstwgt),0) AS s "
            "FROM itemadj WHERE bcode = :b", {"b": bcode}) or {}
        inn = self.db.fetchone(
            "SELECT COALESCE(SUM(towgt),0) AS w, COALESCE(SUM(tostwgt),0) AS s "
            "FROM itemadj WHERE tobcode = :b", {"b": bcode}) or {}
        return (wq(out.get("w")), wq(out.get("s"))), (wq(inn.get("w")), wq(inn.get("s")))

    def history(self, bcode: int) -> list[dict]:
        bcode = int(bcode)
        rows: list[dict] = []
        bc = self.db.fetchone(
            "SELECT tdate, qty, rate, weight, stweight FROM barcode WHERE bcode = :b LIMIT 1",
            {"b": bcode}) if self._has("barcode") else None
        if bc:
            ao, ai = self._adj_sums(bcode)
            rows.append(self._row(bc.get("tdate"), "Created", "", bc.get("qty"), bc.get("rate"),
                                  wq(wq(bc.get("weight")) + ao[0] - ai[0]),
                                  wq(wq(bc.get("stweight")) + ao[1] - ai[1])))
        if self._has("salesm") and self._has("salesd"):
            rows += self._txn("salesm", "salesd", "billno", bcode, "Sales")
        if self._has("salesrm") and self._has("salesrd"):
            rows += self._txn("salesrm", "salesrd", "billno", bcode, "Sales Return")
        rows += self._smith(bcode)
        rows += self._transfers(bcode)
        rows.sort(key=lambda r: (r["tdate"] or "", r["docno"] or ""))
        return rows

    def _txn(self, m: str, d: str, doccol: str, bcode: int, label: str) -> list[dict]:
        ctrl = f"AND {m}.control <= :g" if self._col(m, "control") else ""
        res = self.db.fetchall(
            f"SELECT {m}.tdate, {m}.{doccol} AS docno, {d}.weight, {d}.stonewgt AS stone, "
            f"{d}.qty, {d}.rate FROM {m} JOIN {d} ON {d}.slno = {m}.slno "
            f"WHERE {d}.bcode = :b {ctrl}", {"b": bcode, "g": self.gilevel})
        return [self._row(r.get("tdate"), label, r.get("docno"), r.get("qty"), r.get("rate"),
                          wq(r.get("weight")), wq(r.get("stone"))) for r in res]

    def _smith(self, bcode: int) -> list[dict]:
        if not (self._has("smithm") and self._has("smithd") and self._col("smithd", "bcode")):
            return []
        has_gr = self._col("smithd", "givrec")
        gr = ", smithd.givrec" if has_gr else ""
        ctrl = "AND smithm.control <= :g" if self._col("smithm", "control") else ""
        res = self.db.fetchall(
            f"SELECT smithm.tdate, smithm.docno, smithd.weight, smithd.stonewgt AS stone, smithd.qty{gr} "
            f"FROM smithm JOIN smithd ON smithd.slno = smithm.slno WHERE smithd.bcode = :b {ctrl}",
            {"b": bcode, "g": self.gilevel})
        out = []
        for r in res:
            label = "Smith/Jewl Issue" if (has_gr and str(r.get("givrec") or "") == "G") else "Smith/Jewl Rcpt"
            out.append(self._row(r.get("tdate"), label, r.get("docno"), r.get("qty"), 0,
                                 wq(r.get("weight")), wq(r.get("stone"))))
        return out

    def _transfers(self, bcode: int) -> list[dict]:
        if not self._has("itemadj"):
            return []
        ctrl = "AND control <= :g" if self._col("itemadj", "control") else ""
        out = self.db.fetchall(
            f"SELECT tdate, fromwgt AS weight, fromstwgt AS stone, fromqty AS qty "
            f"FROM itemadj WHERE bcode = :b {ctrl}", {"b": bcode, "g": self.gilevel})
        inn = self.db.fetchall(
            f"SELECT tdate, towgt AS weight, tostwgt AS stone, toqty AS qty "
            f"FROM itemadj WHERE tobcode = :b {ctrl}", {"b": bcode, "g": self.gilevel})
        rows = [self._row(r.get("tdate"), "Transfer Out", "", r.get("qty"), 0,
                          wq(r.get("weight")), wq(r.get("stone"))) for r in out]
        rows += [self._row(r.get("tdate"), "Transfer In", "", r.get("qty"), 0,
                           wq(r.get("weight")), wq(r.get("stone"))) for r in inn]
        return rows

    @staticmethod
    def _row(tdate, txn, docno, qty, rate, weight, stone) -> dict:
        return {"tdate": str(tdate or ""), "transaction": txn, "docno": str(docno or ""),
                "qty": int(qty or 0), "rate": money(rate), "weight": weight, "stone": stone}
