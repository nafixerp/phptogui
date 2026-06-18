"""Customer Opening Bills — port of CustomerOpBillsController::save (core).

Opening sales bills are stored in `salesm` with a billno prefixed 'OP'. Saving
replaces the customer's existing OP bills and re-inserts the supplied rows, each
reserving a serial number. (The party-balance refresh on clients is a documented
follow-on.)
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine


class OpBillError(Exception):
    pass


class CustomerOpBillsService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def bills_for(self, custcode: str) -> list[dict]:
        if not self.pe.db.table_exists("salesm"):
            return []
        return self.pe.db.fetchall(
            "SELECT slno, billno, tdate, billamt FROM salesm "
            "WHERE UPPER(TRIM(custcode)) = :c AND billno LIKE 'OP%' ORDER BY billno",
            {"c": custcode.strip().upper()})

    def save(self, custcode: str, custname: str, rows: list[dict]) -> dict:
        custcode = str(custcode or "").strip().upper()
        if custcode == "":
            raise OpBillError("Customer code is required")
        if not self.pe.db.table_exists("salesm"):
            raise OpBillError("salesm table not found")
        cols = set(self.pe.db.columns("salesm"))
        saved = 0
        with self.pe.db.transaction() as tx:
            tx.execute("DELETE FROM salesm WHERE UPPER(TRIM(custcode)) = :c AND billno LIKE 'OP%'",
                       {"c": custcode})
            for r in rows:
                billno = str(r.get("billno") or "").strip()
                billamt = money(r.get("billamt", 0))
                if billno == "" or billamt <= 0:
                    continue
                slno = self.pe.next_serial_no(tx)
                row = {"slno": slno, "billno": billno, "tdate": r.get("tdate") or None,
                       "custcode": custcode, "custname": str(custname or "").strip(),
                       "billamt": billamt, "netamt": billamt, "control": self.control,
                       "status": 1}
                row = {k: v for k, v in row.items() if k.lower() in cols}
                names = ", ".join(row); binds = ", ".join(f":{k}" for k in row)
                tx.execute(f"INSERT INTO salesm ({names}) VALUES ({binds})", row)
                saved += 1
        log_delpart(self.pe.db, self.session, f"Opening Bills({custcode}) Saved", utype="E", ttype="R")
        return {"saved": saved, "message": f"Saved {saved} opening bill(s)"}
