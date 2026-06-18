"""Order admin operations — Rate Fix + Block/Unblock.

Ports OrderRateFixController::apply and OrderBlockController::block. Both search
`orderm` (control <= gilevel) and refuse to touch a *returned* order
(``status = 2``). Rate-fix writes a ``note`` of the form
``Rate Fixed :<rate> - Dt: dd/mm/yy``; block sets ``blocked`` to Y/N.
"""

from __future__ import annotations

from datetime import date

from ...core.db import Database

RETURNED_STATUS = 2


class OrderAdminError(Exception):
    pass


class OrderAdminService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = max(1, int(gilevel or 1))

    def search(self, q: str = "") -> list[dict]:
        if not self.db.table_exists("orderm"):
            return []
        where = ["control <= :g"]
        params: dict = {"g": self.gilevel}
        if q.strip():
            where.append("(ordno LIKE :q OR custname LIKE :q)"); params["q"] = f"%{q.strip()}%"
        return self.db.fetchall(
            "SELECT TRIM(ordno) AS ordno, TRIM(COALESCE(custname,'')) AS custname, "
            "COALESCE(status,0) AS status, COALESCE(blocked,'N') AS blocked, "
            "COALESCE(billamt,0) AS billamt, tdate, duedate "
            f"FROM orderm WHERE {' AND '.join(where)} ORDER BY slno DESC LIMIT 50", params)

    def _find(self, ordno: str) -> dict:
        row = self.db.fetchone(
            "SELECT slno, COALESCE(status,0) AS status, tdate FROM orderm "
            "WHERE TRIM(ordno) = :o AND control <= :g LIMIT 1",
            {"o": ordno, "g": self.gilevel})
        if not row:
            raise OrderAdminError("This Order number does not exist...")
        return row

    def rate_fix(self, ordno: str, rate) -> str:
        if not self.db.table_exists("orderm"):
            raise OrderAdminError("Order table not found.")
        ordno = str(ordno).strip().upper()
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            raise OrderAdminError("Enter valid rate.")
        if rate <= 0:
            raise OrderAdminError("Enter valid rate.")
        row = self._find(ordno)
        if int(row["status"]) == RETURNED_STATUS:
            raise OrderAdminError("This is not a pending order. You can't edit an order entry which is returned...")
        note = f"Rate Fixed :{rate:.2f} - Dt: {date.today().strftime('%d/%m/%y')}"
        self.db.execute("UPDATE orderm SET note = :n WHERE TRIM(ordno) = :o", {"n": note, "o": ordno})
        return note

    def set_blocked(self, ordno: str, block: bool) -> str:
        if not self.db.table_exists("orderm"):
            raise OrderAdminError("Order table not found.")
        ordno = str(ordno).strip().upper()
        row = self._find(ordno)
        if int(row["status"]) == RETURNED_STATUS:
            raise OrderAdminError("This is not a pending order. You can't block/unblock a returned order.")
        val = "Y" if block else "N"
        self.db.execute("UPDATE orderm SET blocked = :b WHERE TRIM(ordno) = :o", {"b": val, "o": ordno})
        return f"Order {'blocked' if block else 'unblocked'}"
