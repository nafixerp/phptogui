"""Repair Receipt Memo (from party) — port of RepairReceiptMemoPartyController.

Records jewellery received from a customer for repair: a ``repairm`` header
(``givrec = 'R'``) + ``repaird`` rows, plus — when an advance/receipt amount is
collected — a zero-sum two-line cash receipt to the daybook (customer debit,
cash/bank credit). No stock movement. New memos reserve a serial + ``RP/NNNN``
(``REPAIRB`` counter); edit replaces (and clears the old daybook); cancel deletes.
"""

from __future__ import annotations

from datetime import date, datetime

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money, weight as wq
from ...core.posting import PostingEngine, zero_sum


class RepairReceiptMemoError(Exception):
    pass


class RepairReceiptMemoService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None):
        self.pe = engine
        self.db = engine.db
        self.session = session

    def _insert(self, tx, table: str, row: dict) -> None:
        cols = set(self.db.columns(table))
        use = {k: v for k, v in row.items() if k in cols}
        if not use:
            return
        names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
        tx.execute(f"INSERT INTO {table} ({names}) VALUES ({binds})", use)

    def save(self, *, custcode: str, custname: str = "", rows: list[dict],
             tdate: str | None = None, duedate: str = "", sman: str = "",
             recvamt=0, cbcode: str = "CASH", note: str = "", refbill: str = "",
             mode: str = "new", slno: int = 0, bill_no: str = "") -> dict:
        if not (self.db.table_exists("repairm") and self.db.table_exists("repaird")):
            raise RepairReceiptMemoError("Repair tables missing")
        tdate = tdate or date.today().isoformat()
        custcode = str(custcode).strip().upper()
        cbcode = str(cbcode).strip().upper() or "CASH"
        recvamt = money(recvamt)
        norm = []
        for r in rows:
            code = str(r.get("itemcode") or "").strip().upper()
            if not code:
                continue
            w = wq(r.get("weight")); st = wq(r.get("stonewgt"))
            if w <= 0:
                raise RepairReceiptMemoError(f"Please check weight ({code})")
            net = wq(r.get("netwgt")) if r.get("netwgt") not in (None, "") else wq(w - st)
            norm.append({"itemcode": code, "itemname": str(r.get("itemname") or "").strip(),
                         "qty": int(r.get("qty") or 0), "weight": w, "stonewgt": st, "netwgt": net,
                         "complaint": str(r.get("complaint") or "").strip(),
                         "purity": str(r.get("purity") or "").strip(),
                         "stktype": str(r.get("stktype") or "").strip()})
        if not norm:
            raise RepairReceiptMemoError("No item rows to save")
        bill_no = str(bill_no).strip().upper()
        uid = getattr(self.session, "user_code", "") if self.session else ""

        with self.db.transaction() as tx:
            if mode == "edit":
                if slno <= 0 and bill_no:
                    slno = int(tx.scalar("SELECT slno FROM repairm WHERE TRIM(billno) = :b LIMIT 1", {"b": bill_no}) or 0)
                if slno <= 0:
                    raise RepairReceiptMemoError("Bill not found for edit")
                for t in ("repaird", "repairm", "daybook", "daybookpart"):
                    if self.db.table_exists(t):
                        tx.execute(f"DELETE FROM {t} WHERE slno = :s", {"s": slno})
            else:
                slno = self.pe.next_serial_no(tx)
                bill_no = f"RP/{self.pe.increment_gen_int(tx, 'REPAIRB'):04d}"
            self._insert(tx, "repairm", {
                "slno": slno, "billno": bill_no, "tdate": tdate, "duedate": duedate or None,
                "custcode": custcode, "custname": str(custname).strip(), "givrec": "R",
                "control": 1, "status": 1, "sman": str(sman).strip().upper(), "ic": 1,
                "refbillno": refbill, "refbill": refbill, "pamt": recvamt, "ramt": recvamt,
                "recvamt": recvamt, "cbcode": cbcode, "note": note, "remark": note})
            sno = 1
            for r in norm:
                self._insert(tx, "repaird", {
                    "slno": slno, "code": r["itemcode"], "name": r["itemname"], "qty": r["qty"],
                    "weight": r["weight"], "stonewgt": r["stonewgt"], "complaint": r["complaint"],
                    "givrec": "R", "sno": sno, "netwgt": r["netwgt"], "purity": r["purity"],
                    "stktype": r["stktype"]})
                sno += 1
            lines = self._receipt(tx, slno, tdate, bill_no, custcode, str(custname).strip(), cbcode, recvamt, uid)
        return {"slno": slno, "bill_no": bill_no, "items": len(norm),
                "balanced": (money(zero_sum(lines)) == 0) if lines else True}

    def _receipt(self, tx, slno, tdate, bill_no, custcode, custname, cbcode, recvamt, uid) -> list[dict]:
        if recvamt <= 0 or not custcode or not cbcode or not self.db.table_exists("daybook"):
            return []
        part = f"Repair Slip - {bill_no}{(' - ' + custname) if custname else ''}"[:40]
        if self.db.table_exists("daybookpart"):
            self.pe.insert_daybookpart(tx, {"slno": slno, "particular": part, "vchno": bill_no,
                                            "ic": uid, "uid": uid, "ttime": datetime.now().strftime("%H:%M:%S")})
        lines = [{"accode": custcode, "amount": recvamt, "opaccode": cbcode},
                 {"accode": cbcode, "amount": money(-recvamt), "opaccode": custcode}]
        s = 1
        for ln in lines:
            self.pe.insert_daybook_line(tx, {
                "slno": slno, "sno": s, "tdate": tdate, "accode": ln["accode"],
                "amount": ln["amount"], "control": 1, "opaccode": ln["opaccode"]})
            s += 1
        return lines

    def cancel(self, bill_no: str) -> str:
        bill_no = str(bill_no).strip().upper()
        if not bill_no:
            raise RepairReceiptMemoError("Bill no required")
        m = self.db.fetchone("SELECT slno FROM repairm WHERE TRIM(billno) = :b LIMIT 1", {"b": bill_no})
        if not m:
            raise RepairReceiptMemoError("Bill not found")
        with self.db.transaction() as tx:
            for t in ("repaird", "repairm", "daybook", "daybookpart"):
                if self.db.table_exists(t):
                    tx.execute(f"DELETE FROM {t} WHERE slno = :s", {"s": m["slno"]})
        return "Cancelled"
