"""Sales Return posting — port of SalesReturnController save.

All lines use opaccode='ESR'. netamt = billamt + staxamt + astamt; tax reverses
(SGST/CGST or IGST negative); the sales-return account ESR is debited (-billamt):
  cash refund +pamt · customer +(netamt-disc) and -pamt · DISC +disc ·
  SGST/CGST/IGST -tax · ESR -billamt  => balances to zero (astamt assumed 0,
  matching the controller which posts no AST/ROUND line).
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum


class SalesReturnError(Exception):
    pass


def _m(d, k):
    return money(d.get(k, 0))


class SalesReturnService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def build_lines(self, d: dict) -> list[dict]:
        op = "ESR"
        cust = str(d.get("custcode") or "").strip().upper()
        cbcode = str(d.get("cbcode") or "CASH").strip().upper() or "CASH"
        is_cst = bool(d.get("is_cst"))
        billamt = _m(d, "billamt")
        staxamt = _m(d, "staxamt")
        astamt = _m(d, "astamt")
        discount = _m(d, "discount")
        pamt = _m(d, "pamt")
        netamt = money(billamt + staxamt + astamt)
        igst = staxamt if is_cst else Decimal("0")
        cgst = Decimal("0") if is_cst else money(staxamt / 2)
        sgst = Decimal("0") if is_cst else money(staxamt - cgst)

        lines: list[dict] = []

        def add(accode, amount):
            amt = money(amount)
            if not accode or amt == 0:
                return
            lines.append({"accode": accode, "amount": amt, "opaccode": op})

        if pamt > 0:
            add(cbcode, pamt)
        if cust:
            add(cust, money(netamt - discount))
            if pamt > 0:
                add(cust, money(-pamt))
        if discount > 0:
            add("DISC", discount)
        if staxamt > 0:
            if not is_cst:
                add("SGST", money(-sgst))
                add("CGST", money(-cgst))
            else:
                add("IGST", money(-igst))
        if billamt > 0:
            add("ESR", money(-billamt))
        return lines

    def post(self, slno: int, tdate: str, d: dict) -> dict:
        if not self.pe.db.table_exists("daybook"):
            raise SalesReturnError("daybook table not found")
        lines = self.build_lines(d)
        with self.pe.db.transaction() as tx:
            if not slno or int(slno) <= 0:
                slno = self.pe.next_serial_no(tx)
            if self.pe.db.table_exists("daybookpart"):
                bill = str(d.get("billno") or "")
                name = str(d.get("custname") or "")
                self.pe.insert_daybookpart(tx, {
                    "slno": slno, "vchno": "", "tdate": tdate, "control": self.control,
                    "particular": (f"By Sales Return({bill})" + (f" From {name}" if name else ""))[:40],
                })
            sno = 1
            for ln in lines:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": tdate, "accode": ln["accode"],
                    "amount": ln["amount"], "control": self.control, "opaccode": ln["opaccode"],
                })
                sno += 1
        log_delpart(self.pe.db, self.session, f"Sales Return({d.get('billno', '')}) Saved", utype="A", ttype="T")
        return {"slno": slno, "lines": len(lines), "balance": str(zero_sum(lines))}
