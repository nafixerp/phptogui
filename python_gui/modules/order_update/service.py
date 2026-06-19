"""Order Update (manual order entry) — port of OrderUpdateController.

Creates a jewellery order: an ``orderm`` header (status 1, no advance) plus its
``orderd`` item rows, column-filtered to the live schema. The order number is
``<ORDPREF>/NNNNN`` from the ORDERB counter; the slno is a plain SERIALNO+1.
No daybook or stock movement — that happens later at Order Sale. Orders can be
deleted (header + detail).
"""

from __future__ import annotations

from datetime import date

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money, weight as wq
from ...core.posting import PostingEngine


class OrderUpdateError(Exception):
    pass


class OrderUpdateService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None):
        self.pe = engine
        self.db = engine.db
        self.session = session

    def list_orders(self, q: str = "", limit: int = 100) -> list[dict]:
        if not self.db.table_exists("orderm"):
            return []
        where = ["1=1"]
        params: dict = {}
        if q.strip():
            where.append("(ordno LIKE :q OR custname LIKE :q)"); params["q"] = f"%{q.strip()}%"
        return self.db.fetchall(
            "SELECT slno, TRIM(ordno) AS ordno, tdate, duedate, TRIM(COALESCE(custname,'')) AS custname, "
            "COALESCE(billamt,0) AS billamt, COALESCE(status,0) AS status "
            f"FROM orderm WHERE {' AND '.join(where)} ORDER BY slno DESC LIMIT {int(limit)}", params)

    def _ordno(self, tx) -> str:
        prefix = "ORD"
        if self.db.table_exists("generals"):
            p = tx.scalar("SELECT cvalue FROM generals WHERE code = 'ORDPREF'")
            if p and str(p).strip():
                prefix = str(p).strip()
        nxt = self.pe.increment_gen_int(tx, "ORDERB")
        return f"{prefix}/{nxt:05d}"

    def save(self, order: dict, items: list[dict]) -> dict:
        jewlcode = str(order.get("jewlcode") or "").strip()
        custname = str(order.get("custname") or "").strip()
        if not jewlcode or not custname:
            raise OrderUpdateError("Jewellery code and customer name required")
        if not self.db.table_exists("orderm") or not self.db.table_exists("orderd"):
            raise OrderUpdateError("Order tables not found")
        valid = [it for it in items if str(it.get("code") or "").strip()]
        if not valid:
            raise OrderUpdateError("No valid items")

        omcols = set(self.db.columns("orderm"))
        odcols = set(self.db.columns("orderd"))
        tdate = str(order.get("tdate") or "").strip() or date.today().isoformat()
        duedate = str(order.get("duedate") or "").strip() or None
        rate = money(order.get("rate") or self._grate())
        bill_total = sum((money(it.get("amount")) for it in valid), money(0))
        uid = getattr(self.session, "user_code", "") if self.session else ""

        with self.db.transaction() as tx:
            slno = self.pe.increment_gen_int(tx, "SERIALNO")
            ordno = self._ordno(tx)
            mrow = {
                "slno": slno, "ordno": ordno, "tdate": tdate, "duedate": duedate,
                "custcode": str(order.get("custcode") or "").strip(), "custname": custname,
                "rate": rate, "billamt": bill_total, "eamt": 0, "advance": 0, "status": 1,
                "control": 1, "smcode": str(order.get("smcode") or "").strip(), "gadvance": 0,
                "sretamt": 0, "ob": 0, "addr": "", "refund": 0, "closed": 0,
                "jewlcode": jewlcode, "duedate_org": duedate, "ic": uid,
            }
            use = {k: v for k, v in mrow.items() if k in omcols}
            names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
            tx.execute(f"INSERT INTO orderm ({names}) VALUES ({binds})", use)
            sno = 0
            for it in valid:
                sno += 1
                drow = {
                    "slno": slno, "code": str(it.get("code") or "").strip().upper(),
                    "qty": int(it.get("qty") or 0), "weight": wq(it.get("weight")),
                    "stonewgt": wq(it.get("stonewgt")), "stoneprice": money(it.get("stoneprice")),
                    "mcharge": money(it.get("mcharge")), "wastage": wq(it.get("wastage")),
                    "rate": money(it.get("rate") or rate), "amount": money(it.get("amount")),
                    "part": str(it.get("part") or "").strip(), "sno": sno,
                    "iqtype": str(it.get("iqtype") or "").strip(), "smith": "",
                }
                used = {k: v for k, v in drow.items() if k in odcols}
                names = ", ".join(used); binds = ", ".join(f":{k}" for k in used)
                tx.execute(f"INSERT INTO orderd ({names}) VALUES ({binds})", used)
        return {"ordno": ordno, "slno": slno, "items": len(valid)}

    def delete(self, slno: int) -> str:
        slno = int(slno)
        if slno <= 0:
            raise OrderUpdateError("Invalid slno")
        with self.db.transaction() as tx:
            if self.db.table_exists("orderd"):
                tx.execute("DELETE FROM orderd WHERE slno = :s", {"s": slno})
            if self.db.table_exists("orderm"):
                tx.execute("DELETE FROM orderm WHERE slno = :s", {"s": slno})
        return "Order deleted"

    def _grate(self):
        if self.db.table_exists("generald"):
            return self.db.scalar("SELECT cvalue FROM generald WHERE code = 'GRATE'") or 0
        return 0
