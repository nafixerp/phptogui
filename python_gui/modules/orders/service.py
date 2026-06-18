"""Order Bill — port of OrderBillController save + postOrderDaybook (advance).

An order books a commitment in `orderm` (+ `orderd` lines) and posts any advance
received to the daybook:
  effectiveAdvance = advance - refund
  cash/bank legs (cash portion, cc, cheque/CNC) are NEGATIVE (opaccode = customer
  /ADVANCE); the customer/ADVANCE account is credited +effectiveAdvance
  (opaccode = CASH). The advance allocation balances to zero.

Order number reserved from generali.ORDERB (>= max existing). slno from the
shared serial counter. (Bank-commission split + PDC rows: documented follow-on.)
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum

_ORDERM_DEFAULT_COLS = {
    "slno", "ordno", "tdate", "custcode", "custname", "duedate", "rate", "billamt",
    "eamt", "advance", "status", "control", "smcode", "sretamt", "refund", "closed",
    "note", "counter", "taxable", "cbcode", "tax",
}


class OrderError(Exception):
    pass


def _m(d: dict, k: str) -> Decimal:
    return money(d.get(k, 0))


class OrderService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def next_order_number(self) -> int:
        return self.pe.gen_int("ORDERB") + 1

    def build_advance_lines(self, ctx: dict) -> list[dict]:
        op_cust = str(ctx.get("cust_code") or "").strip() or "ADVANCE"
        cbcode = str(ctx.get("cbcode") or "CASH").strip() or "CASH"
        eff = money(_m(ctx, "advance") - _m(ctx, "refund"))
        lines: list[dict] = []
        if eff <= 0:
            return lines
        cc = _m(ctx, "ccamt")
        chq = _m(ctx, "chq_amt")
        chq_pdc = str(ctx.get("chq_pdc") or "N").strip().upper() == "Y"
        chq_bank = str(ctx.get("chq_bank") or "").strip()

        def add(accode, amount, op):
            amt = money(amount)
            if not accode or amt == 0:
                return
            lines.append({"accode": accode, "amount": amt, "opaccode": op})

        cash_part = money(eff - cc - chq)
        if cash_part > 0:
            add(cbcode, money(-cash_part), op_cust)
        if cc > 0:
            add(cbcode, money(-cc), op_cust)
        if chq > 0:
            add("CNC" if chq_pdc else (chq_bank or "CASH"), money(-chq), op_cust)
        add(op_cust, eff, "CASH")
        return lines

    def post_advance(self, slno: int, tdate: str, ctx: dict) -> int:
        lines = self.build_advance_lines(ctx)
        if not lines:
            return 0
        with self.pe.db.transaction() as tx:
            if self.pe.db.table_exists("daybookpart"):
                doc = str(ctx.get("doc_no") or "")
                name = str(ctx.get("cust_name") or "")
                self.pe.insert_daybookpart(tx, {
                    "slno": slno, "tdate": tdate, "control": self.control,
                    "particular": (f"By Order - {doc}" + (f" From {name}" if name else ""))[:40],
                    "vchno": "", "rate": ctx.get("rate") or 0,
                })
            sno = 1
            for ln in lines:
                self.pe.insert_daybook_line(tx, {
                    "slno": slno, "sno": sno, "tdate": tdate, "accode": ln["accode"],
                    "amount": ln["amount"], "control": self.control, "opaccode": ln["opaccode"],
                })
                sno += 1
        return len(lines)

    def _orderm_columns(self) -> set[str]:
        if self.pe.db.table_exists("orderm"):
            return set(self.pe.db.columns("orderm"))
        return _ORDERM_DEFAULT_COLS

    def save(self, header: dict, lines: list[dict] | None = None) -> dict:
        if not self.pe.db.table_exists("orderm"):
            raise OrderError("orderm table not found")
        cust = str(header.get("custcode") or "").strip()
        if cust == "":
            raise OrderError("Customer code is required")
        tdate = str(header.get("tdate") or "").strip()
        if tdate == "":
            raise OrderError("Date is required")

        cols = self._orderm_columns()
        with self.pe.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            ordno = max(self.pe.gen_int("ORDERB"), 0) + 1
            self.pe._set_generali(tx, "ORDERB", ordno)
            row = dict(header)
            row.update({"slno": slno, "ordno": ordno, "control": self.control,
                        "status": str(header.get("status") or "P"),
                        "closed": str(header.get("closed") or "N")})
            row = {k: v for k, v in row.items() if k.lower() in cols}
            names = ", ".join(row); binds = ", ".join(f":{k}" for k in row)
            tx.execute(f"INSERT INTO orderm ({names}) VALUES ({binds})", row)

            if lines and self.pe.db.table_exists("orderd"):
                dcols = set(self.pe.db.columns("orderd"))
                for i, ln in enumerate(lines, 1):
                    lrow = {"slno": slno, "sno": i, **ln}
                    lrow = {k: v for k, v in lrow.items() if k.lower() in dcols}
                    ln_names = ", ".join(lrow); ln_binds = ", ".join(f":{k}" for k in lrow)
                    tx.execute(f"INSERT INTO orderd ({ln_names}) VALUES ({ln_binds})", lrow)

        # advance posting (separate; mirrors the controller's daybook step)
        adv_ctx = {"cust_code": cust, "cust_name": header.get("custname", ""),
                   "doc_no": str(ordno), "rate": header.get("rate", 0),
                   "advance": header.get("advance", 0), "refund": header.get("refund", 0),
                   "cbcode": header.get("cbcode", "CASH"), "ccamt": header.get("ccamt", 0),
                   "chq_amt": header.get("chqamt", 0), "chq_bank": header.get("chq_bank", ""),
                   "chq_pdc": header.get("chq_pdc", "N")}
        posted = self.post_advance(slno, tdate, adv_ctx)
        log_delpart(self.pe.db, self.session, f"Order({ordno}) Added", utype="A", ttype="R")
        return {"slno": slno, "ordno": ordno, "advance_lines": posted, "message": "Order saved"}
