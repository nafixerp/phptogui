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

from datetime import datetime

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money, weight as wq
from ...core.posting import PostingEngine, zero_sum
from ...core.stock_adjust import adjust_item_stock
from ..purchase.service import PurchasePostingService

PR_FLAG = "P"
DMD_FLAG = "Y"
COUNTER_KEY = "DPURCHASEB"
PREFIX_KEY = "DPBPREF"


class DiamondPurchaseSaveError(Exception):
    pass

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


class DiamondPurchaseSaveService:
    """Persist a diamond purchase bill — port of DiamondPurchaseBillController::save.

    Writes the ``purchasem`` header (``pr='P'``, ``dmd='Y'``), the ``purchased``
    item rows and their ``purchased_dmddet`` stone sub-rows, increases item
    stock (purchase in) via ``core/stock_adjust``, and posts the PL daybook by
    reusing ``PurchasePostingService.build_entries``. Document numbering is
    ``DPBPREF``+``DPURCHASEB``; the slno is a reserved global serial.
    """

    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.db = engine.db
        self.session = session
        self.control = int(control or 1)
        self._purchase = PurchasePostingService(engine, session, control)

    def _doc_no(self, tx) -> str:
        prefix = ""
        if self.db.table_exists("generals"):
            p = tx.scalar("SELECT cvalue FROM generals WHERE TRIM(code) = :c", {"c": PREFIX_KEY})
            if p and str(p).strip():
                prefix = str(p).strip()
        nxt = self.pe.increment_gen_int(tx, COUNTER_KEY)
        return f"{prefix}{nxt:05d}"

    def _insert(self, tx, table: str, row: dict) -> None:
        cols = set(self.db.columns(table))
        use = {k: v for k, v in row.items() if k in cols}
        if not use:
            return
        names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
        tx.execute(f"INSERT INTO {table} ({names}) VALUES ({binds})", use)

    def save(self, *, header: dict, items: list[dict], amounts: dict | None = None,
             billdate: str | None = None) -> dict:
        if not self.db.table_exists("purchasem") or not self.db.table_exists("purchased"):
            raise DiamondPurchaseSaveError("Purchase tables not found")
        supp = str(header.get("suppcode") or "").strip().upper()
        if not supp:
            raise DiamondPurchaseSaveError("Supplier code required")
        clean = [it for it in items if str(it.get("code") or it.get("item_code") or "").strip()]
        if not clean:
            raise DiamondPurchaseSaveError("No valid items")
        billdate = billdate or datetime.now().strftime("%Y-%m-%d")
        amounts = dict(amounts or {})
        amounts.setdefault("supplier_code", supp)

        bill_total = sum((money(it.get("amount")) for it in clean), money(0))
        has_dmd = self.db.table_exists("purchased_dmddet")
        # build_entries reads config (general_profile) on its own connection —
        # compute it BEFORE opening the transaction so that read can't roll back
        # the in-flight writes on real MySQL.
        entries = self._purchase.build_entries(amounts)

        with self.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            docno = self._doc_no(tx)
            self._insert(tx, "purchasem", {
                "slno": slno, "docno": docno, "billno": str(header.get("billno") or "").strip(),
                "suppcode": supp, "name": str(header.get("name") or "").strip(),
                "billamt": bill_total, "pr": PR_FLAG, "dmd": DMD_FLAG, "control": self.control,
                "tdate": billdate, "ttime": datetime.now().strftime("%H:%M:%S"),
                "netamt": money(amounts.get("net_total") or bill_total),
                "taxamt": money(amounts.get("tax")), "discount": money(amounts.get("discount")),
                "status": 0, "ic": getattr(self.session, "user_code", "") if self.session else ""})

            sno = 0
            for it in clean:
                sno += 1
                code = str(it.get("code") or it.get("item_code") or "").strip().upper()
                weight = wq(it.get("weight")); qty = int(it.get("qty") or 0)
                stwgt = wq(it.get("stwgt") or it.get("stone_wgt"))
                amount = money(it.get("amount"))
                cost = money(amount / weight) if weight > 0 else money(0)
                stktype = str(it.get("stktype") or "").strip()
                self._insert(tx, "purchased", {
                    "slno": slno, "code": code, "qty": qty, "weight": weight,
                    "rate": money(it.get("rate")), "amount": amount, "cost": cost,
                    "stwgt": stwgt, "stprice": money(it.get("stprice") or it.get("stone_price")),
                    "sno": sno, "stktype": stktype, "mcharge": money(it.get("mcharge")),
                    "touch": money(it.get("touch")), "bcode": str(it.get("barcode") or "").strip(),
                    "dmdamt": money(it.get("dmdamt")), "dmdwgt": wq(it.get("dmdwgt"))})
                # stone sub-rows
                if has_dmd:
                    dsno = 0
                    for dr in (it.get("dmd_rows") or []):
                        if not (int(dr.get("pcs") or 0) or money(dr.get("carats"))):
                            continue
                        dsno += 1
                        self._insert(tx, "purchased_dmddet", {
                            "slno": slno, "prow": sno, "sno": dsno,
                            "code": str(dr.get("stcode") or "").strip(),
                            "sttype": str(dr.get("sttype") or "").strip(),
                            "stcolor": str(dr.get("stcolor") or "").strip(),
                            "stsize": str(dr.get("stsize") or "").strip(),
                            "stcut": str(dr.get("stcut") or "").strip(),
                            "stsettype": str(dr.get("stsettype") or "").strip(),
                            "pcs": int(dr.get("pcs") or 0), "carats": money(dr.get("carats")),
                            "rate": money(dr.get("rate")), "amount": money(dr.get("amount"))})
                # stock increase (purchase in)
                adjust_item_stock(self.db, tx, code, qty, weight, stwgt, stktype, self.control)

            # PL daybook (entries computed above, before the transaction)
            if self.db.table_exists("daybook"):
                if self.db.table_exists("daybookpart"):
                    self.pe.insert_daybookpart(tx, {
                        "slno": slno, "tdate": billdate, "control": self.control,
                        "particular": f"By Diamond Purchase {docno}"[:200], "vchno": docno})
                dsno = 1
                for e in entries:
                    self.pe.insert_daybook_line(tx, {
                        "slno": slno, "sno": dsno, "tdate": billdate, "accode": e["accode"],
                        "amount": e["amount"], "control": self.control, "opaccode": e["opaccode"], "vtype": "PL"})
                    dsno += 1
                residual = money(zero_sum(entries))
                if residual != 0:
                    self.pe.insert_daybook_line(tx, {
                        "slno": slno, "sno": dsno, "tdate": billdate, "accode": "ROUND",
                        "amount": money(-residual), "control": self.control, "opaccode": "EP", "vtype": "PL"})

        return {"slno": slno, "docno": docno, "items": len(clean),
                "balanced": money(zero_sum(entries)) == 0}
