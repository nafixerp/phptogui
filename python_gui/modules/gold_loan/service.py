"""Gold Loan — read path port of GoldLoanController::load + list.

A loan header (`loan`) with pledged items (`loan_items`) and a collection
ledger (`loancolln`). This module provides the lookup/list and load-by-slno
reads; the full disbursement posting (save) is a documented follow-on.
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import money


class GoldLoanService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = max(1, int(gilevel or 1))

    def list(self, date1: str = "", date2: str = "", only_open: bool = False) -> list[dict]:
        if not self.db.table_exists("loan"):
            return []
        cols = set(self.db.columns("loan"))
        where = ["1=1"]
        params: dict = {}
        if "control" in cols:
            where.append("control <= :g"); params["g"] = self.gilevel
        if date1 and date2 and "tdate" in cols:
            where.append("tdate BETWEEN :f AND :t"); params.update(f=date1, t=date2)
        if only_open and "closed" in cols:
            where.append("(closed IS NULL OR closed <> 'Y')")
        cname = "cname" if "cname" in cols else "''"
        return self.db.fetchall(
            f"SELECT slno, docno, tdate, billno, ccode, TRIM(COALESCE({cname},'')) AS cname, "
            "COALESCE(loanamt,0) AS loanamt, COALESCE(totalamt,0) AS totalamt, "
            "COALESCE(closed,'N') AS closed FROM loan "
            f"WHERE {' AND '.join(where)} ORDER BY slno DESC LIMIT 1000", params)

    def load(self, slno: int) -> dict | None:
        if not self.db.table_exists("loan"):
            return None
        loan = self.db.fetchone("SELECT * FROM loan WHERE slno = :s LIMIT 1", {"s": int(slno)})
        if not loan:
            return None
        items = []
        if self.db.table_exists("loan_items"):
            items = self.db.fetchall("SELECT * FROM loan_items WHERE slno = :s", {"s": int(slno)})
        collns = []
        if self.db.table_exists("loancolln"):
            collns = self.db.fetchall(
                "SELECT * FROM loancolln WHERE slno = :s ORDER BY tdate", {"s": int(slno)})
        # balance = total - sum(collections)
        paid = sum((money(c.get("amount")) for c in collns), money(0)) if collns else money(0)
        total = money(loan.get("totalamt") or loan.get("loanamt"))
        return {"loan": loan, "items": items, "collections": collns,
                "paid": paid, "balance": money(total - paid)}
