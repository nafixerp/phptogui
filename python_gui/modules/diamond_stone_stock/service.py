"""Diamond / Stone Stock — port of DiamondStoneStockController::loadSummary.

Item-wise in-stock barcode aggregates (``barcode.stk = 'Y'``) for stone-bearing
items, filtered by ``items.dmdplt`` (D=Diamond, P=Platinum, C=Colour Stone).
Gold weight = gross weight - stone weight. Rows with no stock are dropped.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import weight as wq

_ZERO = Decimal("0")
_DMDPLT = {"Diamond": ("D",), "Platinum": ("P",), "Color Stone": ("C",)}


class DiamondStoneStockService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = int(gilevel or 1)

    def _col(self, t: str, c: str) -> bool:
        return self.db.table_exists(t) and self.db.column_exists(t, c)

    def summary(self, type_: str = "All", stitem: str = "", grpcode: str = "") -> list[dict]:
        if not self.db.table_exists("items") or not self.db.table_exists("barcode"):
            return []
        plts = _DMDPLT.get(type_, ("D", "P"))
        where = ["1=1"]
        params: dict = {}
        if self._col("items", "disabled"):
            where.append("(items.disabled <> 1 OR items.disabled IS NULL)")
        if self._col("items", "showinstkrep"):
            where.append("items.showinstkrep = 'Y'")
        if self._col("items", "dmdplt"):
            ph = ", ".join(f":p{i}" for i in range(len(plts)))
            where.append(f"items.dmdplt IN ({ph})")
            params.update({f"p{i}": v for i, v in enumerate(plts)})
        if grpcode.strip() and self._col("items", "grpcode"):
            where.append("items.grpcode = :gc"); params["gc"] = grpcode.strip()
        dmd_sub = ""
        if self._col("barcode_dmddet", "carats"):
            stf = ""
            if stitem.strip():
                stf = "AND bd.stcode = :st"; params["st"] = stitem.strip()
            dmd_sub = (", COALESCE((SELECT SUM(bd.carats) FROM barcode bc "
                       "JOIN barcode_dmddet bd ON bd.bcode=bc.bcode "
                       f"WHERE bc.icode=items.code AND bc.stk='Y' {stf}),0) AS dmdwgt")
        rows = self.db.fetchall(
            "SELECT items.name, items.code, "
            "COALESCE((SELECT COUNT(bc.bcode) FROM barcode bc WHERE bc.icode=items.code AND bc.stk='Y'),0) AS nos, "
            "COALESCE((SELECT SUM(bc.weight) FROM barcode bc WHERE bc.icode=items.code AND bc.stk='Y'),0) AS gwgt, "
            "COALESCE((SELECT SUM(bc.stweight) FROM barcode bc WHERE bc.icode=items.code AND bc.stk='Y'),0) AS stwgt"
            f"{dmd_sub} FROM items WHERE {' AND '.join(where)} ORDER BY items.name", params)
        out = []
        for r in rows:
            nos = int(r.get("nos") or 0)
            gwgt = wq(r.get("gwgt")); stwgt = wq(r.get("stwgt"))
            if nos <= 0 and gwgt <= 0:
                continue
            out.append({
                "code": str(r.get("code") or "").strip(), "name": str(r.get("name") or "").strip(),
                "nos": nos, "grosswgt": gwgt, "stonewgt": stwgt, "goldwgt": wq(gwgt - stwgt),
                "dmdwgt": wq(r.get("dmdwgt")) if "dmdwgt" in r else _ZERO,
            })
        return out
