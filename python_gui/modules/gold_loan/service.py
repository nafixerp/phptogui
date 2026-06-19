"""Gold Loan — port of GoldLoanController (load + list + save + collection).

A loan header (`loan`) with pledged items (`loan_items`) and a collection
ledger (`loancolln`). Reads cover lookup/list and load-by-slno; the save-path
creates/updates a loan + its pledged items and records repayments (which
recompute the running balance/status). No daybook posting — Gold Loan is a
ledger-only module in the source.

NOTE: the frozen demo `loan` schema differs from the columns this controller
writes (the live app uses a newer loan schema). All writes are therefore
column-filtered to whatever the live `loan`/`loan_items`/`loancolln` tables
actually expose, so the save works against either schema.
"""

from __future__ import annotations

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money
from ...core.posting import PostingEngine


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


class GoldLoanSaveError(Exception):
    pass


class GoldLoanSaveService:
    """Create/update a gold loan and record repayments — port of
    GoldLoanController::save / addCollection. All writes are column-filtered to
    the live schema (the demo `loan` table differs from the controller's)."""

    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.db = engine.db
        self.session = session
        self.control = int(control or 1)

    def _cols(self, table: str) -> set[str]:
        return set(self.db.columns(table)) if self.db.table_exists(table) else set()

    def _filtered(self, table: str, row: dict) -> dict:
        cols = self._cols(table)
        return {k: v for k, v in row.items() if k in cols}

    def _insert(self, tx, table: str, row: dict) -> None:
        use = self._filtered(table, row)
        if not use:
            return
        names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
        tx.execute(f"INSERT INTO {table} ({names}) VALUES ({binds})", use)

    def save(self, header: dict, items: list[dict] | None = None) -> dict:
        if not self.db.table_exists("loan"):
            raise GoldLoanSaveError("Loan table not found in database")
        ccode = str(header.get("ccode") or "").strip()
        loanamt = money(header.get("loan_amount") or header.get("loanamt"))
        if not ccode or loanamt <= 0:
            raise GoldLoanSaveError("Customer and loan amount required")
        slno = int(header.get("slno") or 0)
        tdate = str(header.get("tdate") or "").strip()
        data = {
            "ccode": ccode, "cname": str(header.get("cname") or "").strip(),
            "tdate": tdate, "loanamt": loanamt,
            "intrate": money(header.get("interest_rate") or header.get("intrate") or 12),
            "duedate": str(header.get("due_date") or header.get("duedate") or "").strip() or None,
            "remarks": str(header.get("remarks") or "").strip(), "status": "open",
            "control": self.control,
        }
        with self.db.transaction() as tx:
            if slno > 0:
                use = self._filtered("loan", data)
                if use:
                    sets = ", ".join(f"{k} = :{k}" for k in use)
                    tx.execute(f"UPDATE loan SET {sets} WHERE slno = :slno", {**use, "slno": slno})
                if self.db.table_exists("loan_items"):
                    tx.execute("DELETE FROM loan_items WHERE slno = :s", {"s": slno})
            else:
                slno = self.pe.next_serial_no(tx)
                self._insert(tx, "loan", {**data, "slno": slno})
            if self.db.table_exists("loan_items") and items:
                for it in items:
                    self._insert(tx, "loan_items", {
                        "slno": slno, "icode": str(it.get("icode") or "").strip(),
                        "idesc": str(it.get("idesc") or "").strip(),
                        "purity": money(it.get("purity")), "grosswgt": money(it.get("grosswgt")),
                        "netwgt": money(it.get("netwgt")), "finewgt": money(it.get("finewgt")),
                        "grate": money(it.get("grate")), "value": money(it.get("value"))})
        return {"slno": slno}

    def add_collection(self, slno: int, principal, interest, tdate: str | None = None) -> dict:
        if not self.db.table_exists("loancolln"):
            raise GoldLoanSaveError("loancolln table not found")
        slno = int(slno)
        principal = money(principal); interest = money(interest)
        total = money(principal + interest)
        if slno <= 0 or total <= 0:
            raise GoldLoanSaveError("Invalid data")
        with self.db.transaction() as tx:
            self._insert(tx, "loancolln", {
                "slno": slno, "tdate": tdate or "", "principal": principal,
                "interest": interest, "total": total, "amount": total, "control": self.control})
            if self.db.table_exists("loan"):
                paid = money(tx.scalar(
                    "SELECT COALESCE(SUM(principal),0) FROM loancolln WHERE slno = :s", {"s": slno}))
                loan = tx.fetchall("SELECT loanamt FROM loan WHERE slno = :s LIMIT 1", {"s": slno})
                if loan:
                    balance = money(money(loan[0].get("loanamt")) - paid)
                    status = "closed" if balance <= 0 else "open"
                    upd = self._filtered("loan", {
                        "paidamt": paid, "balance": money(max(money(0), balance)), "status": status,
                        "closed": "Y" if balance <= 0 else "N"})
                    if upd:
                        sets = ", ".join(f"{k} = :{k}" for k in upd)
                        tx.execute(f"UPDATE loan SET {sets} WHERE slno = :slno", {**upd, "slno": slno})
        return {"slno": slno, "total": total}
