"""Stock Period Ledger — port of StockPeriodLedgerController.

For each item matching the filters, computes opening / issued / received /
closing via the shared ``StockCalculator`` over the date range. Supports a
single-item lookup or a full filtered listing (item type, group, sub-group).
"""

from __future__ import annotations

from ...core.db import Database
from ...core.stock import StockCalculator


class StockPeriodLedgerService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = int(gilevel or 1)
        self.calc = StockCalculator(database, gilevel)

    def _col(self, c: str) -> bool:
        return self.db.table_exists("items") and self.db.column_exists("items", c)

    def items(self, itype: str = "", grpcode: str = "", subgrpcode: str = "") -> list[dict]:
        if not self.db.table_exists("items"):
            return []
        where = ["1=1"]
        params: dict = {}
        if self._col("disabled"):
            where.append("(disabled <> 1 OR disabled IS NULL)")
        if self._col("showinstkrep"):
            where.append("(showinstkrep <> 'N' OR showinstkrep IS NULL)")
        if itype and itype in ("G", "S", "O") and self._col("itype"):
            where.append("itype = :it"); params["it"] = itype
        if grpcode.strip() and self._col("grpcode"):
            where.append("grpcode = :gc"); params["gc"] = grpcode.strip()
        if subgrpcode.strip() and self._col("subgrpcode"):
            where.append("subgrpcode = :sg"); params["sg"] = subgrpcode.strip()
        return self.db.fetchall(
            f"SELECT code, name FROM items WHERE {' AND '.join(where)} ORDER BY code LIMIT 5000", params)

    def ledger(self, date1: str, date2: str, itype: str = "", grpcode: str = "",
               subgrpcode: str = "", net_wgt: bool = False, with_stone: bool = False,
               only_with_txn: bool = False) -> list[dict]:
        rows = []
        for it in self.items(itype, grpcode, subgrpcode):
            code = str(it.get("code") or "").strip()
            st = self.calc.calc_item_stock(code, date1, date2, net_wgt, with_stone)
            if only_with_txn and st["opwgt"] == 0 and st["issuedwgt"] == 0 and st["rcvdwgt"] == 0 and st["clwgt"] == 0:
                continue
            rows.append({"code": code, "name": str(it.get("name") or "").strip(), **st})
        return rows

    def item_ledger(self, scode: str, date1: str, date2: str,
                    net_wgt: bool = False, with_stone: bool = False) -> dict:
        scode = str(scode).strip()
        name = ""
        if self.db.table_exists("items"):
            name = str(self.db.scalar("SELECT name FROM items WHERE code = :c", {"c": scode}) or "")
        return {"code": scode, "name": name.strip(),
                **self.calc.calc_item_stock(scode, date1, date2, net_wgt, with_stone)}
