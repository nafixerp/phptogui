"""Barcode Profit Report — port of BarcodeProfitReportController::data.

Sold barcoded items (``salesd`` joined to ``salesm``) with their barcode cost
pulled back from `barcode`, producing per-line cost/profit and stone
cost/profit. Cost rule (mirrors the controller exactly):

  costamt = bc.costamt            if bc.costamt > 0
          = round((wgt-stwgt)*cost, 0)   else if bc.cost > 0
          = round(amount*costperc/100,0) otherwise
  profit  = amount - costamt      if costamt > 0 else 0
  stamt   = stoneprice + dmdamt
  stcost  = bc.coststone + barcode_dmddet.pamt
  stprofit= stamt - stcost
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, quantize, to_decimal

_ZERO = Decimal("0")
_INT = Decimal("1")


class BarcodeProfitService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = int(rlevel or 1)

    def _has(self, t: str) -> bool:
        return self.db.table_exists(t)

    def _col(self, t: str, c: str) -> bool:
        return self._has(t) and self.db.column_exists(t, c)

    def report(self, date1: str, date2: str, grpcode: str = "") -> dict:
        if not self._has("salesm") or not self._has("salesd"):
            return {"rows": [], "totals": self._empty()}
        has_bc = self._has("barcode")
        cost = "(SELECT bc.cost FROM barcode bc WHERE bc.bcode=d.bcode LIMIT 1)" if has_bc else "0"
        costperc = "(SELECT bc.costperc FROM barcode bc WHERE bc.bcode=d.bcode LIMIT 1)" if has_bc else "0"
        costamt = "(SELECT bc.costamt FROM barcode bc WHERE bc.bcode=d.bcode LIMIT 1)" if has_bc else "0"
        coststone = "(SELECT bc.coststone FROM barcode bc WHERE bc.bcode=d.bcode LIMIT 1)" if has_bc else "0"
        dmdcost = ("(SELECT COALESCE(SUM(bd.pamt),0) FROM barcode_dmddet bd WHERE bd.bcode=d.bcode)"
                   if self._has("barcode_dmddet") else "0")
        itemname = "i.name" if self._col("items", "name") else "''"
        where = ["m.tdate BETWEEN :f AND :t", "d.bcode > 0"]
        params: dict = {"f": date1, "t": date2}
        if self._col("salesm", "control"):
            where.append("m.control <= :g"); params["g"] = self.rlevel
        if grpcode.strip() and self._col("items", "grpcode"):
            where.append("i.grpcode = :gc"); params["gc"] = grpcode.strip()
        rows = self.db.fetchall(
            f"SELECT m.tdate, m.billno, d.code AS itemcode, d.bcode, d.qty, d.weight, "
            f"d.amount, d.stonewgt, d.stoneprice, {itemname} AS itemname, "
            f"{cost} AS bc_cost, {costperc} AS bc_costperc, {costamt} AS bccostamt, "
            f"{coststone} AS stcostamt, {dmdcost} AS dmdcostamt "
            "FROM salesd d JOIN salesm m ON m.slno=d.slno "
            "LEFT JOIN items i ON i.code=d.code "
            f"WHERE {' AND '.join(where)} ORDER BY m.tdate, m.slno LIMIT 5000", params)
        out, tot = [], self._empty()
        for r in rows:
            amount = money(r.get("amount"))
            wgt = to_decimal(r.get("weight")) or _ZERO
            stwgt = to_decimal(r.get("stonewgt")) or _ZERO
            stprice = money(r.get("stoneprice"))
            bccostamt = money(r.get("bccostamt"))
            bccost = to_decimal(r.get("bc_cost")) or _ZERO
            bccostperc = to_decimal(r.get("bc_costperc")) or _ZERO
            stcostamt = money(r.get("stcostamt"))
            dmdcostamt = money(r.get("dmdcostamt"))
            if bccostamt > 0:
                ca = bccostamt
            elif bccost > 0:
                ca = quantize((wgt - stwgt) * bccost, _INT)
            else:
                ca = quantize(amount * bccostperc / 100, _INT)
            profit = money(amount - ca) if ca > 0 else _ZERO
            stamt = stprice  # dmdamt from spdmddet omitted unless present
            stcost = money(stcostamt + dmdcostamt)
            stprofit = money(stamt - stcost)
            row = {
                "tdate": str(r.get("tdate") or ""), "billno": str(r.get("billno") or ""),
                "itemcode": str(r.get("itemcode") or ""), "itemname": str(r.get("itemname") or ""),
                "bcode": int(r.get("bcode") or 0), "qty": int(r.get("qty") or 0),
                "weight": wgt, "amount": amount, "costamt": ca, "costperc": bccostperc,
                "profit": profit, "stamt": stamt, "stcost": stcost, "stprofit": stprofit,
            }
            out.append(row)
            tot["qty"] += row["qty"]; tot["weight"] += wgt; tot["amount"] += amount
            tot["costamt"] += ca; tot["profit"] += profit
            tot["stamt"] += stamt; tot["stcost"] += stcost; tot["stprofit"] += stprofit
        tot["count"] = len(out)
        return {"rows": out, "totals": tot}

    @staticmethod
    def _empty() -> dict:
        return {"qty": 0, "weight": _ZERO, "amount": _ZERO, "costamt": _ZERO,
                "profit": _ZERO, "stamt": _ZERO, "stcost": _ZERO, "stprofit": _ZERO, "count": 0}
