"""Order Profit Analysis — port of OrderProfitAnalysisController::loadData.

For each sale that came from an order (``salesm.orderno`` set), compares the
advance taken (amount + weight, from ``orderm`` and ``advafter``) against the
goods actually sold (``salesd`` weight/VA), and books the difference:

  diff = (totSoldWgt - totAdvWgt) * grate + totAdvAmt - totSoldAmt

where totAdvAmt = orderm(advance+sretamt+eamt) + advafter(amount),
      totAdvWgt = orderm(gadvance + (advance+sretamt+eamt)/rate) + advafter(amount/rate),
      totSoldAmt = billamt - salesd(mcharge+stoneprice),
      totSoldWgt = salesd(weight) - salesd(stonewgt).
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, to_decimal, weight as wq

_ZERO = Decimal("0")


class OrderProfitService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = max(1, int(gilevel or 1))

    def _has(self, t: str) -> bool:
        return self.db.table_exists(t)

    def report(self, date1: str, date2: str) -> dict:
        if not self._has("salesm"):
            return {"rows": [], "totals": {"count": 0, "diff": _ZERO}}
        sales = self.db.fetchall(
            "SELECT slno, tdate, billno, orderno, custname, COALESCE(billamt,0) AS billamt, "
            "COALESCE(grate,0) AS grate FROM salesm "
            "WHERE control <= :g AND tdate BETWEEN :f AND :t "
            "AND orderno IS NOT NULL AND TRIM(orderno) <> '' "
            "ORDER BY tdate, billno LIMIT 5000",
            {"g": self.gilevel, "f": date1, "t": date2})
        has_om = self._has("orderm"); has_af = self._has("advafter"); has_sd = self._has("salesd")
        out = []; tot_diff = _ZERO
        for s in sales:
            ordno = str(s.get("orderno") or "").strip()
            slno = s.get("slno")
            grate = to_decimal(s.get("grate")) or _ZERO
            billamt = money(s.get("billamt"))

            advamt1 = advwgt1 = _ZERO
            if has_om and ordno:
                r = self.db.fetchone(
                    "SELECT COALESCE(SUM(advance + sretamt + eamt),0) AS amt, "
                    "COALESCE(SUM(CASE WHEN rate > 0 THEN gadvance + (advance + sretamt + eamt)/rate ELSE 0 END),0) AS wgt "
                    "FROM orderm WHERE TRIM(ordno) = :o", {"o": ordno}) or {}
                advamt1 = money(r.get("amt")); advwgt1 = wq(r.get("wgt"))
            advamt2 = advwgt2 = _ZERO
            if has_af and ordno:
                r = self.db.fetchone(
                    "SELECT COALESCE(SUM(amount),0) AS amt, "
                    "COALESCE(SUM(CASE WHEN rate > 0 THEN amount/rate ELSE 0 END),0) AS wgt "
                    "FROM advafter WHERE TRIM(ordno) = :o", {"o": ordno}) or {}
                advamt2 = money(r.get("amt")); advwgt2 = wq(r.get("wgt"))
            soldwgt = soldstwgt = totva = _ZERO
            if has_sd:
                r = self.db.fetchone(
                    "SELECT COALESCE(SUM(weight),0) AS w, COALESCE(SUM(stonewgt),0) AS sw, "
                    "COALESCE(SUM(mcharge + stoneprice),0) AS va FROM salesd WHERE slno = :s",
                    {"s": slno}) or {}
                soldwgt = wq(r.get("w")); soldstwgt = wq(r.get("sw")); totva = money(r.get("va"))

            tot_adv_amt = money(advamt1 + advamt2)
            tot_adv_wgt = wq(advwgt1 + advwgt2)
            tot_sold_amt = money(billamt - totva)
            tot_sold_wgt = wq(soldwgt - soldstwgt)
            diff = money((tot_sold_wgt - tot_adv_wgt) * grate + tot_adv_amt - tot_sold_amt)
            tot_diff += diff
            out.append({
                "tdate": str(s.get("tdate") or ""), "billno": str(s.get("billno") or ""),
                "orderno": ordno, "custname": str(s.get("custname") or ""),
                "totadvamt": tot_adv_amt, "totadvwgt": tot_adv_wgt,
                "totsoldamt": tot_sold_amt, "totsoldwgt": tot_sold_wgt, "diff": diff,
            })
        return {"rows": out, "totals": {"count": len(out), "diff": money(tot_diff)}}
