"""Item reports — Itemwise Profit, Item Movement, Cost List.

- ``itemwise_profit``: per item over sales (``salesd``+``salesm``, sr='S',
  opbill<>1), sale amount vs cost amount (cost*qty when stkinnos='Y', else
  cost*weight) and profit. Port of ItemwiseProfitController.
- ``item_movement``: per item total qty/weight/amount sold in the period,
  optional item-type filter. Port of ItemMovementController.
- ``cost_list``: items master cost/rate columns. Port of
  ItemReportsController::costList.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, weight as wq

_ZERO = Decimal("0")


class ItemReportsService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = max(1, int(rlevel or 1))

    def _col(self, t: str, c: str) -> bool:
        return self.db.table_exists(t) and self.db.column_exists(t, c)

    def _sales_filters(self, alias: str = "sm") -> str:
        w = []
        if self._col("salesm", "control"):
            w.append(f"{alias}.control <= :g")
        if self._col("salesm", "sr"):
            w.append(f"{alias}.sr = 'S'")
        if self._col("salesm", "opbill"):
            w.append(f"({alias}.opbill <> 1 OR {alias}.opbill IS NULL)")
        return (" AND " + " AND ".join(w)) if w else ""

    def itemwise_profit(self, date1: str, date2: str, itemcode: str = "") -> dict:
        empty = {"rows": [], "totals": {"saleamt": _ZERO, "costamt": _ZERO, "profit": _ZERO,
                                        "tqty": 0, "twgt": _ZERO, "count": 0}}
        if not (self.db.table_exists("salesm") and self.db.table_exists("salesd")
                and self.db.table_exists("items")):
            return empty
        has_stk = self._col("items", "stkinnos")
        has_cost = self._col("salesd", "cost")
        has_amt = self._col("salesd", "amount")
        stk_sel = "i.stkinnos" if has_stk else "'' AS stkinnos"
        saleamt = "SUM(sd.amount)" if has_amt else "0"
        qtycost = "SUM(sd.cost * sd.qty)" if has_cost else "0"
        wgtcost = "SUM(sd.cost * sd.weight)" if has_cost else "0"
        where = ["sm.tdate BETWEEN :f AND :t"]
        params: dict = {"f": date1, "t": date2, "g": self.rlevel}
        if itemcode.strip():
            where.append("UPPER(TRIM(i.code)) = :ic"); params["ic"] = itemcode.strip().upper()
        rows = self.db.fetchall(
            f"SELECT TRIM(i.code) AS code, TRIM(i.name) AS name, {stk_sel}, "
            f"COALESCE({saleamt},0) AS saleamt, COALESCE({qtycost},0) AS qtycostamt, "
            f"COALESCE({wgtcost},0) AS wgtcostamt, COALESCE(SUM(sd.qty),0) AS tqty, "
            f"COALESCE(SUM(sd.weight),0) AS twgt "
            "FROM items i JOIN salesd sd ON sd.code = i.code JOIN salesm sm ON sm.slno = sd.slno "
            f"WHERE {' AND '.join(where)}{self._sales_filters()} "
            f"GROUP BY i.code, i.name{', i.stkinnos' if has_stk else ''} ORDER BY i.name LIMIT 5000", params)
        out = []; tot = {"saleamt": _ZERO, "costamt": _ZERO, "profit": _ZERO, "tqty": 0, "twgt": _ZERO}
        for r in rows:
            saleamt_v = money(r.get("saleamt"))
            costamt = money(r.get("qtycostamt")) if str(r.get("stkinnos") or "").strip() == "Y" else money(r.get("wgtcostamt"))
            profit = money(saleamt_v - costamt)
            if has_amt and saleamt_v <= 0:
                continue
            qty = int(r.get("tqty") or 0); twgt = wq(r.get("twgt"))
            out.append({"code": str(r.get("code") or ""), "name": str(r.get("name") or ""),
                        "tqty": qty, "twgt": twgt, "saleamt": saleamt_v, "costamt": costamt, "profit": profit})
            tot["saleamt"] += saleamt_v; tot["costamt"] += costamt; tot["profit"] += profit
            tot["tqty"] += qty; tot["twgt"] += twgt
        tot["count"] = len(out)
        return {"rows": out, "totals": tot}

    def item_movement(self, date1: str, date2: str, itype: str = "", itemcode: str = "") -> list[dict]:
        if not (self.db.table_exists("salesm") and self.db.table_exists("salesd")
                and self.db.table_exists("items")):
            return []
        has_amt = self._col("salesd", "amount")
        amt = "SUM(sd.amount)" if has_amt else "0"
        where = ["sm.tdate BETWEEN :f AND :t"]
        params: dict = {"f": date1, "t": date2, "g": self.rlevel}
        if itype in ("G", "S", "O") and self._col("items", "itype"):
            where.append("UPPER(SUBSTR(TRIM(i.itype),1,1)) = :it"); params["it"] = itype
        if itemcode.strip():
            where.append("UPPER(TRIM(i.code)) = :ic"); params["ic"] = itemcode.strip().upper()
        rows = self.db.fetchall(
            f"SELECT TRIM(i.code) AS icode, TRIM(i.name) AS iname, COALESCE(SUM(sd.qty),0) AS tot_qty, "
            f"COALESCE(SUM(sd.weight),0) AS tot_wgt, COALESCE({amt},0) AS tot_amt "
            "FROM items i JOIN salesd sd ON sd.code = i.code JOIN salesm sm ON sm.slno = sd.slno "
            f"WHERE {' AND '.join(where)}{self._sales_filters()} "
            "GROUP BY i.code, i.name ORDER BY i.name LIMIT 5000", params)
        return [{"icode": str(r.get("icode") or ""), "iname": str(r.get("iname") or ""),
                 "tot_qty": int(r.get("tot_qty") or 0), "tot_wgt": wq(r.get("tot_wgt")),
                 "tot_amt": money(r.get("tot_amt"))} for r in rows]

    def cost_list(self, itemcode: str = "") -> list[dict]:
        if not self.db.table_exists("items"):
            return []
        where = ["1=1"]
        params: dict = {}
        if self._col("items", "disabled"):
            where.append("(disabled <> 1 OR disabled IS NULL)")
        if itemcode.strip():
            where.append("UPPER(TRIM(code)) = :ic"); params["ic"] = itemcode.strip().upper()
        rows = self.db.fetchall(
            "SELECT TRIM(code) AS code, TRIM(name) AS name, COALESCE(itype,'') AS itype, "
            "COALESCE(cost,0) AS cost, COALESCE(rate,0) AS rate FROM items "
            f"WHERE {' AND '.join(where)} ORDER BY name LIMIT 10000", params)
        return [{"code": str(r.get("code") or ""), "name": str(r.get("name") or ""),
                 "itype": str(r.get("itype") or ""), "cost": money(r.get("cost")),
                 "rate": money(r.get("rate"))} for r in rows]
