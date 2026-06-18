"""Purchase reports (read-only) — purchase book, tax purchase book (day-wise),
monthly, supplier-wise, check list.

Source: PurchaseBookController / TaxPurchaseBookController /
PurchaseCheckListController. Bill-level reads over `purchasem`
(``tdate BETWEEN`` + ``control <= rlevel``), column-guarded so amount columns
absent from the frozen schema default to 0. Optional supplier (suppcode) filter.

purchasem money columns (demo schema): billamt, pamt, addamt, eamt, discount,
netamt, taxamt, astamt, sgst, cgst, igst, hmc, round.
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import money

# candidate amount columns on purchasem (order = display order)
_AMTS = ["billamt", "pamt", "addamt", "eamt", "discount", "taxamt",
         "sgst", "cgst", "igst", "hmc", "round", "netamt"]


class PurchaseReportsService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = int(rlevel or 1)

    def _cols(self) -> set[str]:
        return set(self.db.columns("purchasem")) if self.db.table_exists("purchasem") else set()

    def _amt_cols(self) -> list[str]:
        cols = self._cols()
        return [c for c in _AMTS if c in cols]

    def _where(self, date1: str, date2: str, suppcode: str):
        cols = self._cols()
        where, params = ["1=1"], {}
        if "tdate" in cols:
            where.append("tdate BETWEEN :f AND :t"); params.update(f=date1, t=date2)
        if "control" in cols:
            where.append("control <= :g"); params["g"] = self.rlevel
        if suppcode.strip() and "suppcode" in cols:
            where.append("UPPER(TRIM(suppcode)) = :sc"); params["sc"] = suppcode.strip().upper()
        return " AND ".join(where), params, cols

    def purchase_book(self, date1: str, date2: str, suppcode: str = "") -> dict:
        """Net totals across the period (Net Purchase view)."""
        if not self.db.table_exists("purchasem"):
            return {"totals": {}, "count": 0}
        where, params, _cols = self._where(date1, date2, suppcode)
        amt = self._amt_cols()
        sums = ", ".join(f"COALESCE(SUM({c}),0) AS {c}" for c in amt)
        sel = (sums + ", " if sums else "") + "COUNT(*) AS cnt"
        row = self.db.fetchone(f"SELECT {sel} FROM purchasem WHERE {where}", params) or {}
        totals = {c: money(row.get(c)) for c in amt}
        return {"totals": totals, "count": int(row.get("cnt") or 0)}

    def monthly_purchase(self, date1: str, date2: str, suppcode: str = "") -> list[dict]:
        if not self.db.table_exists("purchasem"):
            return []
        where, params, _cols = self._where(date1, date2, suppcode)
        amt = self._amt_cols()
        sums = ", ".join(f"COALESCE(SUM({c}),0) AS {c}" for c in amt)
        rows = self.db.fetchall(
            f"SELECT SUBSTR(tdate,1,7) AS ym, COUNT(*) AS cnt{(', ' + sums) if sums else ''} "
            f"FROM purchasem WHERE {where} GROUP BY SUBSTR(tdate,1,7) ORDER BY ym", params)
        return [{"month": str(r["ym"]), "count": int(r["cnt"]),
                 **{c: money(r.get(c)) for c in amt}} for r in rows]

    def supplier_wise(self, date1: str, date2: str) -> list[dict]:
        if not self.db.table_exists("purchasem") or "suppcode" not in self._cols():
            return []
        where, params, _cols = self._where(date1, date2, "")
        amt = self._amt_cols()
        sums = ", ".join(f"COALESCE(SUM({c}),0) AS {c}" for c in amt)
        rows = self.db.fetchall(
            f"SELECT TRIM(COALESCE(suppcode,'')) AS suppcode, "
            f"TRIM(COALESCE(MAX(name),'')) AS name, COUNT(*) AS cnt"
            f"{(', ' + sums) if sums else ''} "
            f"FROM purchasem WHERE {where} GROUP BY TRIM(COALESCE(suppcode,'')) "
            f"ORDER BY suppcode", params)
        return [{"suppcode": str(r["suppcode"] or "(none)"), "name": str(r["name"] or ""),
                 "count": int(r["cnt"]), **{c: money(r.get(c)) for c in amt}} for r in rows]

    def check_list(self, date1: str, date2: str, suppcode: str = "") -> list[dict]:
        """Bill-level list. Bill no falls back to docno when billno is blank."""
        if not self.db.table_exists("purchasem"):
            return []
        where, params, cols = self._where(date1, date2, suppcode)
        billno = "billno" if "billno" in cols else "NULL"
        docno = "docno" if "docno" in cols else "NULL"
        net = "netamt" if "netamt" in cols else ("billamt" if "billamt" in cols else "0")
        rows = self.db.fetchall(
            f"SELECT slno, {billno} AS billno, {docno} AS docno, tdate, "
            f"TRIM(COALESCE(name,'')) AS name, COALESCE({net},0) AS netamt "
            f"FROM purchasem WHERE {where} ORDER BY tdate, slno LIMIT 1000", params)
        for r in rows:
            bn = str(r.get("billno") or "").strip()
            r["billno"] = bn if bn else str(r.get("docno") or "").strip()
        return rows
