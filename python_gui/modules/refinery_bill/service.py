"""Refinery Bill (issue) — port of RefineryBillController::save.

Issues metal to a refiner: writes the ``refinerym`` header + ``refineryd``
item rows and decreases item stock (issued out), plus credits the ``TP`` item
with the test-pieces weight. New bills reserve a global serial + an ``RFB/NNNNN``
number (REFINEB counter); editing an existing doc reverses the prior stock,
rewrites the header and replaces the detail rows. Status 1 = forward/issued.
No daybook (pure stock movement on the issue side).
"""

from __future__ import annotations

from datetime import date, datetime

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money, weight as wq
from ...core.posting import PostingEngine
from ...core.stock_adjust import adjust_item_stock

_CONTROL = 1  # "B" book mode


class RefineryBillError(Exception):
    pass


class RefineryBillService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None):
        self.pe = engine
        self.db = engine.db
        self.session = session

    def save(self, *, refiner_code: str, items: list[dict], doc_no: str = "",
             bill_date: str | None = None, sm_code: str = "", test_perc=0,
             exp_wgt=0, note: str = "") -> dict:
        refcode = str(refiner_code).strip().upper()
        if not refcode:
            raise RefineryBillError("Refiner's code empty. You can't save...")
        if not (self.db.table_exists("refinerym") and self.db.table_exists("refineryd")):
            raise RefineryBillError("Refinery tables not found.")
        clean = [r for r in items if str(r.get("item_code") or "").strip()]
        if not clean:
            raise RefineryBillError("Incomplete Transaction. This transaction is not complete...")
        for it in clean:
            if wq(it.get("weight")) <= 0:
                raise RefineryBillError(f"Check Weight ({str(it.get('item_code') or '').strip()}). Weight can't be zero")

        bill_date = bill_date or date.today().isoformat()
        uid = getattr(self.session, "user_code", "") if self.session else ""
        t_testpcs = sum((wq(it.get("test_pcs")) for it in clean), wq(0))
        t_issued = sum((wq(it.get("weight")) for it in clean), wq(0))

        doc_no = str(doc_no).strip()
        existing = None
        if doc_no:
            existing = self.db.fetchone("SELECT slno FROM refinerym WHERE docno = :d LIMIT 1", {"d": doc_no})

        mcols = set(self.db.columns("refinerym"))
        dcols = set(self.db.columns("refineryd"))

        with self.db.transaction() as tx:
            if existing:
                slno = int(existing["slno"])
                self._reverse_stock(tx, slno)
                mrow = {"refcode": refcode, "tdate": bill_date, "toldissuedwgt": wq(t_issued),
                        "status": 1, "ttestpcs": wq(t_testpcs), "smcode": sm_code, "expwgt": wq(exp_wgt)}
                use = {k: v for k, v in mrow.items() if k in mcols}
                sets = ", ".join(f"{k} = :{k}" for k in use)
                tx.execute(f"UPDATE refinerym SET {sets} WHERE slno = :slno", {**use, "slno": slno})
                tx.execute("DELETE FROM refineryd WHERE slno = :s", {"s": slno})
            else:
                slno = self.pe.next_serial_no(tx)
                doc_no = f"RFB/{self.pe.increment_gen_int(tx, 'REFINEB'):05d}"
                mrow = {"slno": slno, "tdate": bill_date, "ttime": datetime.now().strftime("%H:%M:%S"),
                        "docno": doc_no, "refcode": refcode, "tbottlestk": 0, "ttestpcs": wq(t_testpcs),
                        "toldissuedwgt": wq(t_issued), "testperc": money(test_perc), "status": 1,
                        "control": _CONTROL, "smcode": sm_code, "ic": uid, "expwgt": wq(exp_wgt),
                        "note": str(note or "")[:40]}
                use = {k: v for k, v in mrow.items() if k in mcols}
                names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
                tx.execute(f"INSERT INTO refinerym ({names}) VALUES ({binds})", use)

            sno = 1
            for it in clean:
                code = str(it.get("item_code") or "").strip()
                weight = wq(it.get("weight")); qty = int(wq(it.get("qty")))
                stone = wq(it.get("stone_wgt")); testpcs = wq(it.get("test_pcs"))
                stktype = str(it.get("stktype") or "").strip()
                drow = {"slno": slno, "code": code, "issuedwgt": weight, "issuedqty": qty,
                        "status": 1, "cost": money(it.get("cost")), "issuedwgtamt": money(it.get("wgt_amt")),
                        "coper": 0, "mudless": wq(it.get("mud_less")), "sno": sno,
                        "issuedstwgt": stone, "testpcs": testpcs, "rcvdwgt": testpcs, "oissuedwgt": 0,
                        "stktype": stktype, "stktouch": money(it.get("stktouch") or 100),
                        "touch": money(it.get("touch"))}
                use = {k: v for k, v in drow.items() if k in dcols}
                names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
                tx.execute(f"INSERT INTO refineryd ({names}) VALUES ({binds})", use)
                sno += 1
                # decrease issued item stock
                adjust_item_stock(self.db, tx, code, -qty, money(-weight), money(-stone), stktype, _CONTROL)
                # test pieces credited to TP item
                if testpcs > 0:
                    adjust_item_stock(self.db, tx, "TP", 0, testpcs, 0, stktype, _CONTROL)

        return {"doc_no": doc_no, "slno": slno, "items": len(clean)}

    def _reverse_stock(self, tx, slno: int) -> None:
        """Re-add the previously issued stock before a re-save."""
        rows = tx.fetchall(
            "SELECT code, issuedqty, issuedwgt, issuedstwgt, testpcs, stktype "
            "FROM refineryd WHERE slno = :s", {"s": slno})
        for r in rows:
            code = str(r.get("code") or "").strip()
            qty = int(r.get("issuedqty") or 0)
            weight = wq(r.get("issuedwgt")); stone = wq(r.get("issuedstwgt"))
            testpcs = wq(r.get("testpcs")); stktype = str(r.get("stktype") or "").strip()
            adjust_item_stock(self.db, tx, code, qty, weight, stone, stktype, _CONTROL)
            if testpcs > 0:
                adjust_item_stock(self.db, tx, "TP", 0, money(-testpcs), 0, stktype, _CONTROL)
