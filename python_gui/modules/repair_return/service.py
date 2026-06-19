"""Repair Return — port of RepairReturnController::save.

Returns repaired jewellery to the customer: writes the ``repairm`` header +
``repaird`` rows (givrec='G'), decreases item stock (pieces leaving the shop),
bumps the customer's ``clients.balance`` by the net charge, and posts the
charge/receipt to the daybook (account ``RS``, ttype ``RM4``) — always zero-sum
with a ROUND balancer. Editing a bill first reverses the old balance, re-adds
the old stock and clears the old detail + daybook.

Daybook (custCode present):
    cust  -netCharge (op RS)
    bank  -rcvd      (op cust)   ┐ when rcvd != 0
    cust  +rcvd      (op bank)   ┘
    RS    +netCharge (op cust)
    ROUND -residual            (balancer)
with netCharge = amount + taxamt - discount.
"""

from __future__ import annotations

from datetime import datetime

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money, weight as wq
from ...core.posting import PostingEngine, zero_sum
from ...core.stock_adjust import adjust_item_stock

_REPAIR_AC = "RS"
_BAL_COLS = ("balance", "clamt", "opbalance")


class RepairReturnError(Exception):
    pass


class RepairReturnService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.db = engine.db
        self.session = session
        self.control = int(control or 1)

    # -- helpers --------------------------------------------------------------
    def _bal_col(self) -> str | None:
        if not self.db.table_exists("clients"):
            return None
        for c in _BAL_COLS:
            if self.db.column_exists("clients", c):
                return c
        return None

    def _adjust_balance(self, tx, custcode: str, amount) -> None:
        custcode = str(custcode).strip()
        amount = money(amount)
        if not custcode or amount == 0:
            return
        col = self._bal_col()
        if not col:
            return
        tx.execute(f"UPDATE clients SET {col} = COALESCE({col},0) + :a WHERE TRIM(code) = :c",
                   {"a": amount, "c": custcode})

    def _reverse_stock(self, tx, slno: int) -> None:
        rows = tx.fetchall(
            "SELECT code, qty, weight, stonewgt, stktype FROM repaird WHERE slno = :s", {"s": slno})
        for r in rows:
            code = str(r.get("code") or "").strip()
            if not code:
                continue
            adjust_item_stock(self.db, tx, code, int(r.get("qty") or 0), wq(r.get("weight")),
                              wq(r.get("stonewgt")), str(r.get("stktype") or "").strip(), self.control)

    def _insert(self, tx, table: str, row: dict) -> None:
        cols = set(self.db.columns(table))
        use = {k: v for k, v in row.items() if k in cols}
        if not use:
            return
        names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
        tx.execute(f"INSERT INTO {table} ({names}) VALUES ({binds})", use)

    # -- main -----------------------------------------------------------------
    def save(self, header: dict, rows: list[dict], mode: str = "new") -> dict:
        if not (self.db.table_exists("repairm") and self.db.table_exists("repaird")):
            raise RepairReturnError("Repair tables missing")
        custcode = str(header.get("custcode") or "").strip().upper()
        custname = str(header.get("custname") or "").strip()
        sman = str(header.get("sman") or "").strip().upper()
        rbillno = str(header.get("rbillno") or "").strip().upper()
        amount = money(header.get("amount"))
        discount = money(header.get("discount"))
        rcvd = money(header.get("rcvd"))
        taxperc = money(header.get("taxperc"))
        taxamt = money(header.get("taxamt"))
        cashbank = str(header.get("cashbank_code") or "").strip().upper() or "CASH"
        tdate = str(header.get("tdate") or "").strip() or datetime.now().strftime("%Y-%m-%d")

        norm = []
        for r in rows:
            code = str(r.get("itemcode") or "").strip().upper()
            if not code:
                continue
            w = wq(r.get("weight"))
            if w <= 0:
                raise RepairReturnError(f"Check Weight ({code}). You can't save...")
            norm.append({"itemcode": code, "itemname": str(r.get("itemname") or "").strip(),
                         "qty": int(r.get("qty") or 0), "weight": w, "stonewgt": wq(r.get("stonewgt")),
                         "netwgt": wq(r.get("netwgt")), "wastage": wq(r.get("wastage")),
                         "mcharge": money(r.get("mcharge")), "amount": money(r.get("amount")),
                         "rate": money(r.get("rate")), "cost": money(r.get("cost")),
                         "stktype": str(r.get("stktype") or "").strip()})
        if not norm:
            raise RepairReturnError("No item rows to save")
        if not sman:
            raise RepairReturnError("Select salesman")
        if amount <= 0:
            raise RepairReturnError("It is an empty bill. You can't save...")

        slno = int(header.get("slno") or 0)
        billno = str(header.get("bill_no") or "").strip().upper()

        with self.db.transaction() as tx:
            if mode == "edit":
                if slno <= 0 and billno:
                    slno = int(tx.scalar("SELECT slno FROM repairm WHERE TRIM(billno) = :b LIMIT 1",
                                         {"b": billno}) or 0)
                if slno <= 0:
                    raise RepairReturnError("Bill not found for edit")
                old = tx.fetchall("SELECT custcode, amount, taxamt, discount, rcvd FROM repairm WHERE slno = :s",
                                  {"s": slno})
                if old:
                    o = old[0]
                    old_bal = money(money(o.get("amount")) + money(o.get("taxamt"))
                                    - money(o.get("discount")) - money(o.get("rcvd")))
                    self._adjust_balance(tx, str(o.get("custcode") or ""), money(-old_bal))
                self._reverse_stock(tx, slno)
                tx.execute("DELETE FROM repaird WHERE slno = :s", {"s": slno})
                tx.execute("DELETE FROM repairm WHERE slno = :s", {"s": slno})
                if self.db.table_exists("daybook"):
                    tx.execute("DELETE FROM daybook WHERE slno = :s", {"s": slno})
                if self.db.table_exists("daybookpart"):
                    tx.execute("DELETE FROM daybookpart WHERE slno = :s", {"s": slno})
            else:
                slno = self.pe.next_serial_no(tx)
                billno = f"RM4/{self.pe.increment_gen_int(tx, 'RM4B'):05d}"

            self._insert(tx, "repairm", {
                "slno": slno, "billno": billno, "tdate": tdate, "custcode": custcode,
                "custname": custname, "amount": amount, "discount": discount, "rcvd": rcvd,
                "givrec": "G", "control": self.control, "status": 1, "rbillno": rbillno,
                "sman": sman, "taxperc": taxperc, "taxamt": taxamt, "ic": 1})

            sno = 1
            for r in norm:
                adjust_item_stock(self.db, tx, r["itemcode"], -r["qty"], money(-r["weight"]),
                                  money(-r["stonewgt"]), r["stktype"], self.control)
                self._insert(tx, "repaird", {
                    "slno": slno, "code": r["itemcode"], "name": r["itemname"], "qty": r["qty"],
                    "weight": r["weight"], "stonewgt": r["stonewgt"], "netwgt": r["netwgt"],
                    "wastage": r["wastage"], "mcharge": r["mcharge"], "amount": r["amount"],
                    "rate": r["rate"], "cost": r["cost"], "givrec": "G", "sno": sno,
                    "stktype": r["stktype"], "addwgt": r["netwgt"]})
                sno += 1

            balance = money(amount + taxamt - discount - rcvd)
            self._adjust_balance(tx, custcode, balance)
            lines = self._post_daybook(tx, slno, billno, tdate, custcode, custname,
                                       amount, taxamt, discount, rcvd, cashbank)

        log_delpart(self.db, self.session,
                    f"Repair Return({billno}) {'Updated' if mode == 'edit' else 'Saved'}",
                    utype="E" if mode == "edit" else "A", ttype="T")
        return {"slno": slno, "bill_no": billno, "balanced": money(zero_sum(lines)) == 0, "lines": len(lines)}

    def _post_daybook(self, tx, slno, billno, tdate, custcode, custname,
                      amount, taxamt, discount, rcvd, cashbank) -> list[dict]:
        if not self.db.table_exists("daybook"):
            return []
        if self.db.table_exists("daybookpart"):
            self.pe.insert_daybookpart(tx, {
                "slno": slno, "vchno": billno,
                "particular": f"By Repair Voucher ({billno}) To {custname}"[:100],
                "taxamt": taxamt, "ttime": datetime.now().strftime("%H:%M:%S")})
        netcharge = money(amount + taxamt - discount)
        lines: list[dict] = []
        if custcode and netcharge != 0:
            lines.append({"accode": custcode, "amount": money(-netcharge), "opaccode": _REPAIR_AC})
        if rcvd != 0:
            lines.append({"accode": cashbank, "amount": money(-rcvd), "opaccode": custcode or _REPAIR_AC})
            if custcode:
                lines.append({"accode": custcode, "amount": rcvd, "opaccode": cashbank})
        if netcharge != 0:
            lines.append({"accode": _REPAIR_AC, "amount": netcharge, "opaccode": custcode or cashbank or "CASH"})
        residual = money(zero_sum(lines))
        if residual != 0:
            lines.append({"accode": "ROUND", "amount": money(-residual), "opaccode": _REPAIR_AC})
        sno = 1
        for ln in lines:
            self.pe.insert_daybook_line(tx, {
                "slno": slno, "sno": sno, "tdate": tdate, "accode": ln["accode"][:20],
                "amount": ln["amount"], "control": self.control, "opaccode": ln["opaccode"][:20],
                "ttype": "RM4"})
            sno += 1
        return lines
