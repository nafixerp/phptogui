"""Order Cancel — port of OrderCancelController / OrderBillController::cancelBill.

Finds the order by order number, reverses its advance posting (deletes the
order's daybook + daybookpart rows, and pdclist/daybookratewgt where present),
and marks the orderm row closed.
"""

from __future__ import annotations

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import to_decimal


class OrderCancelError(Exception):
    pass


class OrderCancelService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session

    def search(self, term: str = "") -> list[dict]:
        if not self.db.table_exists("orderm"):
            return []
        sql = "SELECT slno, ordno, custname, tdate, status, closed FROM orderm"
        params: dict = {}
        if term.strip():
            params["s"] = f"%{term.strip()}%"
            sql += " WHERE CAST(ordno AS CHAR) LIKE :s OR custname LIKE :s"
        sql += " ORDER BY slno DESC LIMIT 300"
        return self.db.fetchall(sql, params)

    def _slno_for_ordno(self, ordno) -> int:
        v = self.db.scalar("SELECT slno FROM orderm WHERE ordno = :o LIMIT 1",
                           {"o": int(to_decimal(ordno) or 0)})
        return int(v or 0)

    def cancel(self, ordno) -> dict:
        if not self.db.table_exists("orderm"):
            raise OrderCancelError("orderm table not found")
        slno = self._slno_for_ordno(ordno)
        if slno <= 0:
            raise OrderCancelError("Order not found")
        with self.db.transaction() as tx:
            if self.db.table_exists("daybook"):
                tx.execute("DELETE FROM daybook WHERE slno = :s", {"s": slno})
            if self.db.table_exists("daybookpart"):
                tx.execute("DELETE FROM daybookpart WHERE slno = :s", {"s": slno})
            for t in ("pdclist", "daybookratewgt"):
                if self.db.table_exists(t):
                    tx.execute(f"DELETE FROM {t} WHERE slno = :s", {"s": slno})
            sets = "closed = 'Y'"
            if self.db.column_exists("orderm", "status"):
                sets += ", status = 9"   # 9 = cancelled marker
            tx.execute(f"UPDATE orderm SET {sets} WHERE slno = :s", {"s": slno})
        log_delpart(self.db, self.session, f"Order({int(to_decimal(ordno) or 0)}) Cancelled", utype="D", ttype="R")
        return {"slno": slno, "message": "Order cancelled"}
