"""PDC Collection / Clearance — port of PdcCollectionController::actionSave.

Clears a post-dated cheque: posts the bank/party movement to the daybook and
marks the originating ``pdclist`` row collected. Voucher series depends on
receipt/payment (``rp``) and control level:

    R+1 VRB/ · R+2 'VRE ' · P+1 VPB/ · P+2 'VPE '

Daybook lines (signs flip for payments, ``rp='P'``):
    party  +amount        (op = bank)
    bank   -net           (op = party)          [net = amount - bankexpense]
    BEXP   -(exp+scharge) (op = bank)  if expense+scharge != 0
    SCHARGE +scharge      (op = bank)  if scharge != 0
These balance to zero given ``net = amount - expense`` (BEXP+SCHARGE = -expense).
Bounce reverses the cheque instead.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum

_VCH = {("R", 1): ("VRB/", "VCHNORB"), ("R", 2): ("VRE ", "VCHNORE"),
        ("P", 1): ("VPB/", "VCHNOPB"), ("P", 2): ("VPE ", "VCHNOPE")}


class PdcCollectionError(Exception):
    pass


class PdcCollectionService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None):
        self.pe = engine
        self.db = engine.db
        self.session = session

    def collect(self, *, chequeno: str, tdate: str, party_code: str, bank: str,
                amount, net_amount, expense=0, scharge=0, chqdate: str | None = None,
                bounce: bool = False, sidocno: str = "", control: int | None = None) -> dict:
        if not (self.db.table_exists("pdclist") and self.db.table_exists("daybook")
                and self.db.table_exists("daybookpart")):
            raise PdcCollectionError("Required tables missing")
        chequeno = str(chequeno).strip().upper()
        party_code = str(party_code).strip().upper()
        bank = str(bank).strip().upper()
        amount = money(amount); net = money(net_amount)
        expense = money(expense); scharge = money(scharge)
        if not tdate:
            raise PdcCollectionError("Valid date required")
        if not chequeno or not party_code or not bank or net <= 0:
            raise PdcCollectionError("Incomplete entry. Cheque, Party, Bank and Net amount are required")

        base = self.db.fetchone(
            "SELECT MAX(slno) AS slno, MAX(TRIM(rp)) AS rp, MAX(control) AS control, "
            "MAX(TRIM(particulars)) AS particulars FROM pdclist WHERE TRIM(chqno) = :c",
            {"c": chequeno}) or {}
        srp = str(base.get("rp") or "R").strip().upper()
        srp = "P" if srp == "P" else "R"
        ctrl = int(control or base.get("control") or 1)
        if ctrl <= 0:
            ctrl = 1
        if not sidocno.strip():
            sidocno = str(self.db.scalar(
                "SELECT docno FROM pdclist WHERE TRIM(chqno) = :c ORDER BY slno DESC LIMIT 1",
                {"c": chequeno}) or "").strip()

        uid = getattr(self.session, "user_code", "") if self.session else ""
        dtexpense = money(expense + scharge)

        with self.db.transaction() as tx:
            prefix, counter = _VCH[(srp, 2 if ctrl >= 2 else 1)]
            vchno = f"{prefix}{self.pe.increment_gen_int(tx, counter):05d}"
            slno = self.pe.next_serial_no(tx)

            part = (f"Cheque Bounced for {chequeno}-{party_code}" if bounce
                    else f"{str(base.get('particulars') or '').strip()} > Cheque Clearance for {chequeno}".strip())[:100]
            self.pe.insert_daybookpart(tx, {
                "slno": slno, "vchno": vchno, "particular": part, "chequeno": chequeno,
                "chequedate": chqdate, "uid": uid, "tdate": tdate,
                "ttime": datetime.now().strftime("%H:%M:%S")})

            lines = []

            def post(accode, amt, op):
                amt = money(amt)
                if amt == 0:
                    return
                lines.append({"accode": accode, "amount": amt, "opaccode": op})

            sign = (lambda v: money(-v)) if srp == "P" else (lambda v: money(v))
            if bounce:
                post(party_code, sign(amount + expense + scharge), bank)
                if dtexpense > 0:
                    post(bank, (money(-dtexpense) if srp == "P" else dtexpense), party_code)
            else:
                post(party_code, sign(amount), bank)
                post(bank, (net if srp == "P" else money(-net)), party_code)
                if dtexpense != 0:
                    post("BEXP", (dtexpense if srp == "P" else money(-dtexpense)), bank)
                if scharge != 0:
                    post("SCHARGE", (money(-scharge) if srp == "P" else scharge), bank)

            sno = 1
            for ln in lines:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": tdate, "accode": ln["accode"],
                    "amount": ln["amount"], "control": ctrl, "opaccode": ln["opaccode"]})
                sno += 1

            if sidocno:
                tx.execute(
                    "UPDATE pdclist SET pend = 'N', colndate = :cd, slno2 = :s2, "
                    "bankexp = :be, scharge = :sc, bounced = :bn WHERE TRIM(docno) = :d",
                    {"cd": tdate, "s2": slno, "be": expense, "sc": scharge,
                     "bn": "Y" if bounce else "N", "d": sidocno})

        return {"slno": slno, "vchno": vchno, "balanced": money(zero_sum(lines)) == 0, "lines": len(lines)}
