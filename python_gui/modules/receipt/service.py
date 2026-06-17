"""Receipt voucher — port of ReceiptController::actionSave / actionDelete.

Posting (docs/accounting-posting-logic.md):
  * Party account:  +(amount + discount), opaccode = cash/bank
  * Cash/Bank:      -(amount),            opaccode = party
  * Discount (if>0): -(discount) to RDISCAC (default DISC), opaccode = party
  => party credit == cash/bank debit + discount debit (sum == 0).

Voucher numbering: VRB//VRE/ (or VRC/ when cash/bank-separate numbering is on);
PDC -> pdclist + PDCR. Edit reuses the slno + supplied vchno; delete removes all
rows for the slno.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine


class ReceiptError(Exception):
    pass


def _money(v) -> Decimal:
    return money(v).copy_abs()


class ReceiptService:
    VOUCHER = "receipt"

    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    # -- voucher numbering --------------------------------------------------
    def _next_vchno(self, tx, cbcode: str, is_pdc: bool) -> str:
        if is_pdc:
            if self.control == 1:
                return self.pe.reserve_voucher(tx, "PDCR/", "PDCRB", 4)
            return self.pe.reserve_voucher(tx, "PDCR", "PDCRE", 4)
        separate = self.pe.general_profile("BankCashSeperateVoucherNo", "N").strip().upper() == "Y"
        if self.control == 1 and separate and cbcode and self.pe.db.table_exists("accountm"):
            if self.pe.account_actype2(cbcode) == "B":
                return self.pe.reserve_voucher(tx, "VRB/", "VCHNORB")
            return self.pe.reserve_voucher(tx, "VRC/", "VCHNORC")
        if self.control == 1:
            return self.pe.reserve_voucher(tx, "VRB/", "VCHNORB")
        return self.pe.reserve_voucher(tx, "VRE/", "VCHNORE")

    def preview_vchno(self, cbcode: str = "") -> str:
        separate = self.pe.general_profile("BankCashSeperateVoucherNo", "N").strip().upper() == "Y"
        if self.control == 1 and separate and cbcode and self.pe.db.table_exists("accountm"):
            if self.pe.account_actype2(cbcode) == "B":
                return self.pe.preview_voucher("VRB/", "VCHNORB")
            return self.pe.preview_voucher("VRC/", "VCHNORC")
        return self.pe.preview_voucher("VRB/" if self.control == 1 else "VRE/",
                                       "VCHNORB" if self.control == 1 else "VCHNORE")

    # -- posting lines (also used by tests for the zero-sum invariant) ------
    def build_lines(self, slno, tdate, cbcode, accode, amount, discount) -> list[dict]:
        amount = _money(amount)
        discount = _money(discount)
        lines = [
            {"slno": slno, "tdate": tdate, "accode": accode,
             "amount": money(amount + discount), "control": self.control, "opaccode": cbcode},
            {"slno": slno, "tdate": tdate, "accode": cbcode,
             "amount": money(-amount), "control": self.control, "opaccode": accode},
        ]
        if discount > 0:
            disc_acc = self.pe.general_profile("RDISCAC", "DISC")
            lines.append({"slno": slno, "tdate": tdate, "accode": disc_acc,
                          "amount": money(-discount), "control": self.control, "opaccode": accode})
        return lines

    def save(self, form: dict, mode: str = "A") -> dict:
        mode = str(mode or "A").strip().upper()
        tdate = str(form.get("tdate") or "").strip()
        cbcode = str(form.get("cbcode") or "").strip().upper()
        accode = str(form.get("accode") or "").strip().upper()
        amount = _money(form.get("amount", 0))
        discount = _money(form.get("discount", 0))
        is_pdc = bool(form.get("pdc"))

        if tdate == "":
            raise ReceiptError("Valid date is required")
        if cbcode == "":
            raise ReceiptError("Cash/Bank account is required")
        if accode == "":
            raise ReceiptError("Account code is required")
        if amount <= 0:
            raise ReceiptError("Amount must be greater than zero")
        if not self.pe.db.table_exists("accountm"):
            raise ReceiptError("Account master table not found.")
        if not self.pe.account_exists(cbcode):
            raise ReceiptError(f"Cash/Bank account '{cbcode}' not found. Cannot save.")
        if not self.pe.account_exists(accode):
            raise ReceiptError(f"Account code '{accode}' not found. Cannot save.")

        edit_slno = int(form.get("slno") or 0)
        with self.pe.db.transaction() as tx:
            if mode == "E" and edit_slno > 0:
                self.pe.delete_voucher(tx, edit_slno)
                lslno = edit_slno
                svchno = str(form.get("vchno") or "").strip()
            else:
                lslno = self.pe.next_serial_no(tx)
                svchno = self._next_vchno(tx, cbcode, is_pdc)

            if is_pdc and self.pe.db.table_exists("pdclist"):
                pdc = {"slno": lslno, "tdate": tdate, "docno": svchno, "bank": cbcode,
                       "code": accode, "chqno": str(form.get("chequeno") or "").strip(),
                       "chqdate": form.get("chequedate") or None, "amount": money(amount),
                       "particulars": str(form.get("particular") or "")[:200], "rp": "R",
                       "pend": "Y", "control": self.control}
                cols = set(self.pe.db.columns("pdclist"))
                pdc = {k: v for k, v in pdc.items() if k.lower() in cols}
                names = ", ".join(pdc); binds = ", ".join(f":{k}" for k in pdc)
                tx.execute(f"INSERT INTO pdclist ({names}) VALUES ({binds})", pdc)
            else:
                self.pe.insert_daybookpart(tx, {
                    "slno": lslno, "vchno": svchno,
                    "particular": str(form.get("particular") or "")[:200],
                    "staff": str(form.get("staff") or "").strip(),
                    "chequeno": str(form.get("chequeno") or "").strip(),
                    "chequedate": form.get("chequedate") or None,
                    "duedate": form.get("duedate") or None,
                    "rate": form.get("rate") or 0, "taxperc": form.get("taxperc") or 0,
                    "taxamt": form.get("taxamt") or 0, "discount": money(discount),
                    "interstate": "Y" if form.get("interstate") else "N",
                    "taxreverse": "Y" if form.get("taxreverse") else "N",
                    "tdate": tdate, "control": self.control,
                    "ic": (self.session.user_code if self.session else ""),
                    "ttime": self.pe.now_time(),
                })
                for line in self.build_lines(lslno, tdate, cbcode, accode, amount, discount):
                    self.pe.insert_daybook_line(tx, line)

        log_delpart(self.pe.db, self.session, f"Receipt({svchno}) {'Updated' if mode == 'E' else 'Added'}",
                    utype="E" if mode == "E" else "A", ttype="R")
        return {"slno": lslno, "vchno": svchno, "message": "Receipt saved successfully"}

    def delete(self, slno: int) -> str:
        slno = int(slno or 0)
        if slno <= 0:
            raise ReceiptError("Invalid slno")
        with self.pe.db.transaction() as tx:
            self.pe.delete_voucher(tx, slno)
        log_delpart(self.pe.db, self.session, f"Receipt(slno {slno}) Deleted", utype="D", ttype="R")
        return "Receipt deleted successfully"
