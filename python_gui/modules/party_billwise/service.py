"""Party bill-wise Receipt / Payment — ports of
CustomerBillwiseRcptController and SupplierBillwisePaymentController (mirror
images of each other).

A receipt (customer) or payment (supplier) is allocated against open bills:
each selected bill bumps the master's *after* column (``salesm.ramtafter`` /
``purchasem.pamtafter``) and writes a ``collection`` row, then the totals post
a two-line daybook voucher (always zero-sum). Any discount posts a second
journal voucher.

                receipt (customer)        payment (supplier)
  voucher       VRB//VRE/ (VCHNOR*)       VPB//VPE/ (VCHNOP*)
  cash a/c      CASH                      <cash/bank>
  daybook       party +T / cash -T        party -T / cash +T
  discount      party +D / DISC -D        party -D / PDISC +D
  master after  ramtafter += alocamt      pamtafter += alocamt
"""

from __future__ import annotations

from decimal import Decimal

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money
from ...core.posting import PostingEngine


class PartyBillwiseError(Exception):
    pass


_MODES = {
    "receipt": {"sign": Decimal("1"), "master": "salesm", "after": "ramtafter",
                "disc_ac": "DISC", "vch": {1: ("VRB/", "VCHNORB"), 2: ("VRE/", "VCHNORE")},
                "jvch": {1: ("JLB/", "VCHNOJB"), 2: ("JLE/", "VCHNOJE")}, "default_cash": "CASH"},
    "payment": {"sign": Decimal("-1"), "master": "purchasem", "after": "pamtafter",
                "disc_ac": "PDISC", "vch": {1: ("VPB/", "VCHNOPB"), 2: ("VPE/", "VCHNOPE")},
                "jvch": {1: ("JLB/", "VCHNOJB"), 2: ("JLE/", "VCHNOJE")}, "default_cash": "CASH"},
}


class PartyBillwiseService:
    def __init__(self, engine: PostingEngine, mode: str = "receipt",
                 session: AppSession | None = None, control: int = 1):
        if mode not in _MODES:
            raise ValueError(mode)
        self.pe = engine
        self.db = engine.db
        self.mode = mode
        self.cfg = _MODES[mode]
        self.session = session
        self.control = control if control in (1, 2) else 1

    def _insert(self, tx, table: str, row: dict) -> None:
        cols = set(self.db.columns(table))
        use = {k: v for k, v in row.items() if k in cols}
        if not use:
            return
        names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
        tx.execute(f"INSERT INTO {table} ({names}) VALUES ({binds})", use)

    def _voucher(self, tx, table_key: str) -> str:
        prefix, counter = self.cfg[table_key][self.control]
        return f"{prefix}{self.pe.increment_gen_int(tx, counter):05d}"

    def post(self, *, partycode: str, tdate: str, items: list[dict], grate=0,
             smcode: str = "", part: str = "", cbcode: str = "") -> dict:
        if not tdate:
            raise PartyBillwiseError("Invalid date")
        partycode = str(partycode).strip().upper()
        if not partycode:
            raise PartyBillwiseError("No party selected")
        grate = money(grate)
        sign = self.cfg["sign"]
        cash_ac = (str(cbcode).strip().upper() or self.cfg["default_cash"]) if self.mode == "payment" else self.cfg["default_cash"]
        master = self.cfg["master"]
        after = self.cfg["after"]

        for it in items:
            if money(it.get("alocamt")) > money(it.get("balance")) + Decimal("0.005"):
                raise PartyBillwiseError(
                    f"Allocated amt ({it.get('billno')}) is greater than balance. You can't Save...")

        uid = getattr(self.session, "user_code", "") if self.session else ""
        rcvd_total = money(0); disc_total = money(0)
        has_alloc = False

        with self.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            vchno = self._voucher(tx, "vch")
            has_after = self.db.table_exists(master) and self.db.column_exists(master, after)
            has_due = self.db.table_exists(master) and self.db.column_exists(master, "duedate")

            for it in items:
                alocamt = money(it.get("alocamt")); discamt = money(it.get("discamt"))
                selected = bool(it.get("selected"))
                if not selected and alocamt == 0 and discamt == 0:
                    continue
                has_alloc = True
                islno = int(it.get("slno") or it.get("islno") or 0)
                billno = str(it.get("billno") or "").strip()
                duedate = str(it.get("duedate") or "").strip() or tdate
                bill_grate = money(it.get("grate"))
                eff_grate = max(grate, bill_grate)
                if alocamt == 0 and discamt != 0:
                    eff_grate = money(0)
                if islno > 0 and has_after:
                    sets = f"{after} = COALESCE({after},0) + :a"
                    p = {"a": alocamt, "s": islno}
                    if has_due:
                        sets += ", duedate = :d"; p["d"] = duedate
                    tx.execute(f"UPDATE {master} SET {sets} WHERE slno = :s", p)
                if self.db.table_exists("collection"):
                    self._insert(tx, "collection", {
                        "slno": slno, "code": partycode, "tdate": tdate, "billno": billno,
                        "tranamt": alocamt, "discount": discamt, "duedate": duedate,
                        "control": self.control, "islno": islno, "grate": eff_grate,
                        "grate2": grate, "cbcode": cash_ac})
                rcvd_total += alocamt; disc_total += discamt

            if not has_alloc and rcvd_total == 0 and disc_total == 0:
                return {"slno": slno, "vchno": vchno, "saved": False}

            if not part.strip():
                part = (f"Adjustment Entry {partycode} - {vchno}" if (rcvd_total == 0 and disc_total != 0)
                        else f"{'Receipt from' if self.mode == 'receipt' else 'Payment to'} {partycode} - {vchno}")
            self._insert(tx, "daybookpart", {
                "slno": slno, "vchno": vchno, "particular": part[:40], "staff": smcode,
                "tdate": tdate, "ic": smcode, "uid": uid, "control": self.control})

            if rcvd_total != 0:
                self._daybook_pair(tx, slno, tdate, partycode, money(sign * rcvd_total),
                                   cash_ac, money(-sign * rcvd_total))

            if disc_total != 0:
                slno2 = self.pe.next_serial_no(tx)
                vchno2 = self._voucher(tx, "jvch")
                self._insert(tx, "daybookpart", {
                    "slno": slno2, "vchno": vchno2, "particular": f"Adjustment Entry {partycode} - {vchno2}"[:40],
                    "staff": smcode, "tdate": tdate, "ic": smcode, "uid": uid, "control": self.control})
                self._daybook_pair(tx, slno2, tdate, partycode, money(sign * disc_total),
                                   self.cfg["disc_ac"], money(-sign * disc_total))

        return {"slno": slno, "vchno": vchno, "saved": True,
                "received": rcvd_total, "discount": disc_total}

    def _daybook_pair(self, tx, slno, tdate, ac1, amt1, ac2, amt2) -> None:
        for sno, (ac, amt) in enumerate(((ac1, amt1), (ac2, amt2)), start=1):
            self._insert(tx, "daybook", {
                "slno": slno, "sno": sno, "tdate": tdate, "accode": ac,
                "amount": money(amt), "control": self.control,
                "opaccode": ac2 if sno == 1 else ac1})
