"""Order Advance-After — port of OrderAdvanceAfterController::save.

Records a further advance (or refund) taken against an already-open order
(``orderm.status = 1``). Optional metal items go to ``orderdga`` and increase
item stock; the cash advance posts a two-line daybook voucher (customer/ADVANCE
debit, cash-bank credit) numbered VRB//VRE/ for a receipt or VPB//VPE/ for a
refund, and an ``advafter`` ledger row is written. Editing reverses the prior
stock + records and re-applies. Always zero-sum on the daybook.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money, weight as wq
from ...core.posting import PostingEngine, zero_sum
from ...core.stock_adjust import adjust_item_stock

_CONTROL = 1  # advance posting is forced to level 1 (Bill)


class OrderAdvanceAfterError(Exception):
    pass


class OrderAdvanceAfterService:
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

    def save(self, *, ordno: str, tdate: str, amount, rate=0, cashbank_code: str = "CASH",
             amttowgt: bool = False, items: list[dict] | None = None, edit_slno: int = 0) -> dict:
        ordno = str(ordno).strip().upper()
        if not ordno:
            raise OrderAdvanceAfterError("Order number is required")
        if not self.db.table_exists("orderm"):
            raise OrderAdvanceAfterError("Order table missing")
        tdate = str(tdate).strip() or datetime.now().strftime("%Y-%m-%d")
        amount = money(amount); rate = money(rate)
        cbcode = str(cashbank_code).strip().upper() or "CASH"
        items = items or []
        if amount == 0 and not items:
            raise OrderAdvanceAfterError("Amount is not entered. You can't save.")

        order = self.db.fetchone(
            "SELECT custcode FROM orderm WHERE TRIM(ordno) = :o AND status = 1 LIMIT 1", {"o": ordno})
        if not order:
            raise OrderAdvanceAfterError("Invalid order number. Order does not exist or is not active.")
        custcode = str(order.get("custcode") or "").strip()
        saccode = custcode if custcode else "ADVANCE"
        cashwgt = wq(amount / rate) if (amttowgt and rate > 0) else wq(0)
        uid = getattr(self.session, "user_code", "") if self.session else ""

        with self.db.transaction() as tx:
            if int(edit_slno) > 0:
                slno = int(edit_slno)
                self._reverse(tx, slno)
            else:
                slno = self.pe.next_serial_no(tx)

            dtwgt = wq(0); sno = 0
            if items and self.db.table_exists("orderdga"):
                for it in items:
                    code = str(it.get("code") or "").strip().upper()
                    w = wq(it.get("weight"))
                    if not code or w == 0:
                        continue
                    sno += 1
                    qty = int(it.get("qty") or 0); stw = wq(it.get("stonewgt"))
                    lesswgt = wq(it.get("lesswgt")); stktype = str(it.get("stktype") or "").strip()
                    self._insert(tx, "orderdga", {
                        "slno": slno, "sno": sno, "code": code, "qty": qty, "weight": w,
                        "cost": money(it.get("cost")), "stktype": stktype, "stonewgt": stw,
                        "lessperc": money(it.get("lessperc")), "lesswgt": lesswgt,
                        "iqtype": str(it.get("iqtype") or "").strip(), "stktouch": 100,
                        "tdate": tdate, "control": _CONTROL})
                    dtwgt = wq(dtwgt + (w - stw - lesswgt))
                    adjust_item_stock(self.db, tx, code, qty, w, stw, stktype, _CONTROL)
            dtwgt = wq(dtwgt + cashwgt)

            is_receipt = amount > 0 or dtwgt > 0
            prefix, counter = (("VRB/", "VCHNORB") if is_receipt else ("VPB/", "VCHNOPB"))
            vchno = f"{prefix}{self.pe.increment_gen_int(tx, counter):05d}"

            if amount != 0 or dtwgt != 0:
                self._insert(tx, "advafter", {
                    "slno": slno, "tdate": tdate, "docno": vchno, "ordno": ordno, "ttype": "C",
                    "amount": amount, "control": _CONTROL, "rate": rate, "wgt": dtwgt,
                    "amttowgt": "Y" if amttowgt else "N"})

            lines = []
            if amount != 0 and self.db.table_exists("daybook"):
                particular = f"Advance Against {ordno}" if is_receipt else f"Refund Against {ordno}"
                if self.db.table_exists("daybookpart"):
                    self.pe.insert_daybookpart(tx, {
                        "slno": slno, "vchno": vchno, "particular": particular,
                        "ic": uid, "ttime": datetime.now().strftime("%H:%M:%S")})
                lines = [{"accode": saccode, "amount": amount, "opaccode": cbcode},
                         {"accode": cbcode, "amount": money(-amount), "opaccode": saccode}]
                s = 1
                for ln in lines:
                    self.pe.insert_daybook_line(tx, {
                        "slno": slno, "sno": s, "tdate": tdate, "accode": ln["accode"],
                        "amount": ln["amount"], "control": _CONTROL, "opaccode": ln["opaccode"]})
                    s += 1
        return {"slno": slno, "vchno": vchno, "dtwgt": dtwgt,
                "balanced": money(zero_sum(lines)) == 0 if lines else True}

    def _reverse(self, tx, slno: int) -> None:
        if self.db.table_exists("orderdga"):
            for oi in tx.fetchall("SELECT code, qty, weight, stonewgt, stktype FROM orderdga WHERE slno = :s", {"s": slno}):
                code = str(oi.get("code") or "").strip()
                if code:
                    adjust_item_stock(self.db, tx, code, -int(oi.get("qty") or 0), money(-wq(oi.get("weight"))),
                                      money(-wq(oi.get("stonewgt"))), str(oi.get("stktype") or "").strip(), _CONTROL)
            tx.execute("DELETE FROM orderdga WHERE slno = :s", {"s": slno})
        for t in ("advafter", "daybook", "daybookpart"):
            if self.db.table_exists(t):
                tx.execute(f"DELETE FROM {t} WHERE slno = :s", {"s": slno})
