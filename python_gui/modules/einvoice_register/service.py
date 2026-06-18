"""e-Invoice Register — port of EInvoiceRegisterController::data / details.

Read register over `e_invoices` (the IRN/ack ledger written by the e-invoicing
provider) with date / status / free-text filters, and a single-row detail load
that exposes the stored request/response JSON payloads.
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import money

_STATUS = {"generated", "cancelled", "failed"}


class EInvoiceRegisterService:
    def __init__(self, database: Database):
        self.db = database

    def register(self, date1: str = "", date2: str = "", status: str = "", q: str = "") -> list[dict]:
        if not self.db.table_exists("e_invoices"):
            return []
        where = ["1=1"]
        params: dict = {}
        if date1:
            where.append("bill_date >= :f"); params["f"] = date1
        if date2:
            where.append("bill_date <= :t"); params["t"] = date2
        if status.strip().lower() in _STATUS:
            where.append("status = :st"); params["st"] = status.strip().lower()
        if q.strip():
            where.append("(bill_no LIKE :q OR customer_name LIKE :q OR irn LIKE :q OR ack_no LIKE :q)")
            params["q"] = f"%{q.strip()}%"
        rows = self.db.fetchall(
            "SELECT id, bill_no, bill_date, customer_code, customer_name, gst_no, "
            "COALESCE(net_total,0) AS net_total, status, irn, ack_no, ack_date, "
            "generated_at, cancelled_at FROM e_invoices "
            f"WHERE {' AND '.join(where)} ORDER BY generated_at DESC, id DESC LIMIT 2000", params)
        for r in rows:
            r["net_total"] = money(r.get("net_total"))
        return rows

    def details(self, bill_no: str) -> dict | None:
        if not self.db.table_exists("e_invoices"):
            return None
        return self.db.fetchone(
            "SELECT * FROM e_invoices WHERE bill_no = :b ORDER BY id DESC LIMIT 1",
            {"b": str(bill_no).strip()})
