"""Diamond Purchase bills — port of DiamondPurchaseBillController.

Diamond purchases live in the **same** `purchasem` / `purchased` tables as
regular purchases, distinguished by ``pr = 'P'`` and ``dmd = 'Y'``. The
stone breakup for each item line is stored in `purchased_dmddet`, keyed by
``slno`` + ``prow`` (the 1-based position of the parent `purchased` row).

The daybook side is identical to a regular purchase (``vtype = 'PL'``), so
posting reuses ``PurchasePostingService`` — this module adds the read/register
path (list bills, load a bill with its diamond sub-rows) and the
diamond-purchase document-number preview (prefix ``DPBPREF`` + ``DPURCHASEB``
counter).

Source: DiamondPurchaseBillController::index/data/get/generateBillNumber.
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import money

PR_FLAG = "P"
DMD_FLAG = "Y"
COUNTER_KEY = "DPURCHASEB"
PREFIX_KEY = "DPBPREF"

_AMTS = ["billamt", "pamt", "addamt", "eamt", "discount", "taxamt",
         "sgst", "cgst", "igst", "netamt"]


class DiamondPurchaseService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = int(rlevel or 1)

    def _cols(self) -> set[str]:
        return set(self.db.columns("purchasem")) if self.db.table_exists("purchasem") else set()

    def _flag_where(self, cols: set[str]) -> str:
        """Restrict to diamond purchases when the flag columns exist."""
        parts = []
        if "pr" in cols:
            parts.append("pr = :pr")
        if "dmd" in cols:
            parts.append("dmd = :dmd")
        return (" AND " + " AND ".join(parts)) if parts else ""

    def list_bills(self, date1: str, date2: str, suppcode: str = "") -> list[dict]:
        if not self.db.table_exists("purchasem"):
            return []
        cols = self._cols()
        where = ["1=1"]
        params: dict = {"pr": PR_FLAG, "dmd": DMD_FLAG}
        if "tdate" in cols:
            where.append("tdate BETWEEN :f AND :t"); params.update(f=date1, t=date2)
        if "control" in cols:
            where.append("control <= :g"); params["g"] = self.rlevel
        if suppcode.strip() and "suppcode" in cols:
            where.append("UPPER(TRIM(suppcode)) = :sc"); params["sc"] = suppcode.strip().upper()
        net = "netamt" if "netamt" in cols else "billamt"
        billno = "billno" if "billno" in cols else "NULL"
        docno = "docno" if "docno" in cols else "NULL"
        rows = self.db.fetchall(
            f"SELECT slno, {docno} AS docno, {billno} AS billno, tdate, "
            f"TRIM(COALESCE(name,'')) AS name, suppcode, "
            f"COALESCE(billamt,0) AS billamt, COALESCE({net},0) AS netamt "
            f"FROM purchasem WHERE {' AND '.join(where)}{self._flag_where(cols)} "
            "ORDER BY tdate, slno LIMIT 1000", params)
        return rows

    def get_bill(self, docno: str) -> dict | None:
        """Header + item lines, each carrying its grouped diamond sub-rows."""
        if not self.db.table_exists("purchasem"):
            return None
        cols = self._cols()
        head = self.db.fetchone(
            f"SELECT * FROM purchasem WHERE UPPER(TRIM(docno)) = :d{self._flag_where(cols)} LIMIT 1",
            {"d": str(docno).strip().upper(), "pr": PR_FLAG, "dmd": DMD_FLAG})
        if not head:
            return None
        slno = head["slno"]
        items = []
        if self.db.table_exists("purchased"):
            order = "ORDER BY sno" if self.db.column_exists("purchased", "sno") else ""
            items = self.db.fetchall(
                f"SELECT * FROM purchased WHERE slno = :s {order}", {"s": slno})
        dmd_map = self._dmd_rows(slno)
        for idx, it in enumerate(items, start=1):
            it["dmd_rows"] = dmd_map.get(idx, [])
        return {"header": head, "items": items}

    def _dmd_rows(self, slno) -> dict[int, list[dict]]:
        if not self.db.table_exists("purchased_dmddet"):
            return {}
        rows = self.db.fetchall(
            "SELECT prow, sno, code, sttype, stcolor, stsize, stcut, stsettype, "
            "pcs, carats, rate, amount FROM purchased_dmddet WHERE slno = :s "
            "ORDER BY prow, sno", {"s": slno})
        out: dict[int, list[dict]] = {}
        for r in rows:
            prow = int(r.get("prow") or 0)
            out.setdefault(prow, []).append({
                "stcode": str(r.get("code") or "").strip(),
                "sttype": str(r.get("sttype") or "").strip(),
                "stcolor": str(r.get("stcolor") or "").strip(),
                "stsize": str(r.get("stsize") or "").strip(),
                "stcut": str(r.get("stcut") or "").strip(),
                "stsettype": str(r.get("stsettype") or "").strip(),
                "pcs": int(r.get("pcs") or 0),
                "carats": money(r.get("carats")),
                "rate": money(r.get("rate")),
                "amount": money(r.get("amount")),
            })
        return out

    def next_doc_no(self) -> str:
        """Preview the next diamond-purchase doc number (DPBPREF + DPURCHASEB)."""
        prefix = ""
        if self.db.table_exists("generals"):
            prefix = str(self.db.scalar(
                "SELECT cvalue FROM generals WHERE TRIM(code) = :c", {"c": PREFIX_KEY}) or "").strip()
        nxt = 0
        if self.db.table_exists("generali"):
            nxt = int(self.db.scalar(
                "SELECT cvalue FROM generali WHERE TRIM(code) = :c", {"c": COUNTER_KEY}) or 0)
        return f"{prefix}{nxt + 1:05d}"
