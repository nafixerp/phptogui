"""Stock Summary (cost-wise / rate-wise) — port of
StockSummaryCostWiseController / StockSummaryRateWiseController getTransactions.

Period transaction summary split by metal: Gold/Silver sales and sales returns
(weight + amount) and Gold/Silver/Old-Gold/Old-Silver purchases. Cost-wise
values sales at ``weight * cost``; rate-wise values them at ``salesd.amount``.
The closing-stock / smith / party balance blocks are a documented follow-on.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, weight as wq

_ZERO = Decimal("0")


class StockSummaryService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.g = int(gilevel or 1)

    def _has(self, *t: str) -> bool:
        return all(self.db.table_exists(x) for x in t)

    def _agg(self, sql: str, params: dict) -> dict:
        r = self.db.fetchone(sql, params) or {}
        return {"wgt": wq(r.get("wgt")), "amt": money(r.get("amt"))}

    def transactions(self, date1: str, date2: str, costwise: bool = True) -> dict:
        out = {k: {"wgt": _ZERO, "amt": _ZERO} for k in (
            "gold_sales", "silver_sales", "gold_salesret", "silver_salesret",
            "og_purch", "gold_purch", "silver_purch", "os_purch")}
        p = {"d1": date1, "d2": date2, "g": self.g}
        sales_amt = "d.weight * d.cost" if costwise else "d.amount"
        if self._has("salesd", "salesm", "items"):
            for key, itype in (("gold_sales", "G"), ("silver_sales", "S")):
                out[key] = self._agg(
                    f"SELECT COALESCE(SUM(d.weight),0) wgt, COALESCE(SUM({sales_amt}),0) amt "
                    "FROM salesd d JOIN salesm m ON m.slno=d.slno JOIN items i ON i.code=d.code "
                    "WHERE m.tdate>=:d1 AND m.tdate<=:d2 AND m.control<=:g AND i.itype=:it",
                    {**p, "it": itype})
        if self._has("salesrd", "salesrm", "items"):
            for key, itype in (("gold_salesret", "G"), ("silver_salesret", "S")):
                out[key] = self._agg(
                    f"SELECT COALESCE(SUM(d.weight),0) wgt, COALESCE(SUM({sales_amt}),0) amt "
                    "FROM salesrd d JOIN salesrm m ON m.slno=d.slno JOIN items i ON i.code=d.code "
                    "WHERE m.tdate>=:d1 AND m.tdate<=:d2 AND m.control<=:g AND i.itype=:it",
                    {**p, "it": itype})
        if self._has("purchased", "purchasem"):
            out["og_purch"] = self._agg(
                "SELECT COALESCE(SUM(d.weight),0) wgt, COALESCE(SUM(d.amount),0) amt "
                "FROM purchased d JOIN purchasem m ON m.slno=d.slno "
                "WHERE d.code='OG' AND m.tdate>=:d1 AND m.tdate<=:d2 AND m.control<=:g", p)
            out["os_purch"] = self._agg(
                "SELECT COALESCE(SUM(d.weight),0) wgt, COALESCE(SUM(d.amount),0) amt "
                "FROM purchased d JOIN purchasem m ON m.slno=d.slno "
                "WHERE d.code='OS' AND m.tdate>=:d1 AND m.tdate<=:d2 AND m.control<=:g", p)
            if self.db.table_exists("items"):
                out["gold_purch"] = self._agg(
                    "SELECT COALESCE(SUM(d.weight),0) wgt, COALESCE(SUM(d.amount),0) amt "
                    "FROM purchased d JOIN purchasem m ON m.slno=d.slno JOIN items i ON i.code=d.code "
                    "WHERE i.itype='G' AND d.code<>'OG' AND m.tdate>=:d1 AND m.tdate<=:d2 AND m.control<=:g", p)
                out["silver_purch"] = self._agg(
                    "SELECT COALESCE(SUM(d.weight),0) wgt, COALESCE(SUM(d.amount),0) amt "
                    "FROM purchased d JOIN purchasem m ON m.slno=d.slno JOIN items i ON i.code=d.code "
                    "WHERE i.itype='S' AND d.code<>'OS' AND m.tdate>=:d1 AND m.tdate<=:d2 AND m.control<=:g", p)
        return out
