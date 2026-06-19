"""Remake Issue Memo (to party) — port of RemakeIssueMemoPartyController.

A memo of items issued to a goldsmith/party for remake: a ``smithm`` header
(``doctype = 'Remake Issue'``) plus its ``smithd`` rows (``givrec = 'G'``). It is
a memo only — no stock movement or daybook posting. New memos reserve a serial +
an ``RM2/NNNN`` number (ISSUEPARTY counter); edit replaces; cancel deletes.
"""

from __future__ import annotations

from datetime import date

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import weight as wq
from ...core.posting import PostingEngine


class RemakeIssueMemoError(Exception):
    pass


class RemakeIssueMemoService:
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

    def save(self, *, custcode: str, rows: list[dict], tdate: str | None = None,
             duedate: str = "", sman: str = "", mode: str = "new",
             slno: int = 0, bill_no: str = "") -> dict:
        if not (self.db.table_exists("smithm") and self.db.table_exists("smithd")):
            raise RemakeIssueMemoError("smith tables missing")
        tdate = tdate or date.today().isoformat()
        custcode = str(custcode).strip().upper()
        sman = str(sman).strip().upper()
        norm = []
        for r in rows:
            code = str(r.get("itemcode") or "").strip().upper()
            if not code:
                continue
            w = wq(r.get("weight")); st = wq(r.get("stonewgt"))
            if w <= 0:
                raise RemakeIssueMemoError(f"Please check weight ({code})")
            net = wq(r.get("netwgt")) if r.get("netwgt") not in (None, "") else wq(w - st)
            norm.append({"itemcode": code, "itemname": str(r.get("itemname") or "").strip(),
                         "qty": int(r.get("qty") or 0), "weight": w, "stonewgt": st, "netwgt": net,
                         "remark": str(r.get("complaint") or "").strip(),
                         "stktype": str(r.get("stktype") or "").strip()})
        if not norm:
            raise RemakeIssueMemoError("No item rows to save")
        bill_no = str(bill_no).strip().upper()

        with self.db.transaction() as tx:
            if mode == "edit":
                if slno <= 0 and bill_no:
                    slno = int(tx.scalar("SELECT slno FROM smithm WHERE TRIM(docno) = :b LIMIT 1", {"b": bill_no}) or 0)
                if slno <= 0:
                    raise RemakeIssueMemoError("Bill not found for edit")
                tx.execute("DELETE FROM smithd WHERE slno = :s", {"s": slno})
                tx.execute("DELETE FROM smithm WHERE slno = :s", {"s": slno})
            else:
                slno = self.pe.next_serial_no(tx)
                bill_no = f"RM2/{self.pe.increment_gen_int(tx, 'ISSUEPARTY'):04d}"
            self._insert(tx, "smithm", {
                "slno": slno, "docno": bill_no, "tdate": tdate, "duedate": duedate or None,
                "smithcode": custcode, "smcode": sman, "status": 1, "control": 1, "ic": 1,
                "doctype": "Remake Issue"})
            sno = 1
            for r in norm:
                self._insert(tx, "smithd", {
                    "slno": slno, "sno": sno, "code": r["itemcode"], "name": r["itemname"],
                    "qty": r["qty"], "weight": r["weight"], "stonewgt": r["stonewgt"],
                    "netwgt": r["netwgt"], "givrec": "G", "stktype": r["stktype"], "remark": r["remark"]})
                sno += 1
        return {"slno": slno, "bill_no": bill_no, "items": len(norm)}

    def cancel(self, bill_no: str) -> str:
        bill_no = str(bill_no).strip().upper()
        if not bill_no:
            raise RemakeIssueMemoError("Bill no required")
        if not self.db.table_exists("smithm"):
            raise RemakeIssueMemoError("smith tables missing")
        m = self.db.fetchone("SELECT slno FROM smithm WHERE TRIM(docno) = :b LIMIT 1", {"b": bill_no})
        if not m:
            raise RemakeIssueMemoError("Bill not found")
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM smithd WHERE slno = :s", {"s": m["slno"]})
            tx.execute("DELETE FROM smithm WHERE slno = :s", {"s": m["slno"]})
        return "Cancelled"
