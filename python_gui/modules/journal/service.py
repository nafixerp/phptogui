"""Journal voucher — port of JournalController::actionSave / actionDelete.

A balanced multi-line voucher: each row is a single account with EITHER a debit
(amountd) or a credit (amountc). Debit -> daybook.amount negative; credit ->
positive. opaccode = first credit account (for debit rows) / first debit account
(for credit rows). Debit total must equal credit total. vchno: JLB/ (level 1) or
JLE/ via VCHNOJB/VCHNOJE counters.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money
from ...core.posting import PostingEngine, zero_sum


class JournalError(Exception):
    pass


class JournalService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def _validate_rows(self, rows: list[dict]):
        clean = []
        dd_total = Decimal("0")
        dc_total = Decimal("0")
        first_debit = ""
        first_credit = ""
        for r in rows:
            acc = str(r.get("particulars") or "").strip().upper()
            amountd = money(r.get("amountd", 0)).copy_abs()
            amountc = money(r.get("amountc", 0)).copy_abs()
            if acc == "" or (amountd <= 0 and amountc <= 0):
                continue
            if amountd > 0 and amountc > 0:
                raise JournalError("Debit and credit cannot both be entered in same row")
            if not self.pe.account_exists(acc):
                raise JournalError(f"Invalid account code: {acc}")
            if amountd > 0:
                dd_total += amountd
                if first_debit == "":
                    first_debit = acc
            else:
                dc_total += amountc
                if first_credit == "":
                    first_credit = acc
            clean.append({"acc": acc, "amountd": amountd, "amountc": amountc,
                          "rownote": str(r.get("rownote") or "").strip()[:100]})
        if not clean:
            raise JournalError("Empty entry. You cannot save")
        if money(dd_total) != money(dc_total):
            raise JournalError("Debit and credit totals are not equal")
        return clean, first_debit, first_credit

    def build_lines(self, slno, tdate, clean, first_debit, first_credit) -> list[dict]:
        lines = []
        for r in clean:
            is_debit = r["amountd"] > 0
            amount = money(-r["amountd"]) if is_debit else money(r["amountc"])
            op = first_credit if is_debit else first_debit
            lines.append({"slno": slno, "tdate": tdate, "accode": r["acc"], "amount": amount,
                          "control": self.control, "opaccode": op, "narration": r["rownote"]})
        return lines

    def save(self, rows: list[dict], tdate: str, narration: str = "",
             mode: str = "A", slno: int = 0, vchno: str = "") -> dict:
        if not self.pe.db.table_exists("daybook") or not self.pe.db.table_exists("daybookpart"):
            raise JournalError("Required tables missing")
        tdate = str(tdate or "").strip()
        if tdate == "":
            raise JournalError("Valid date required")
        if not rows:
            raise JournalError("Empty entry. You cannot save")
        mode = str(mode or "A").strip().upper()[:1]
        if mode not in ("A", "E"):
            mode = "A"

        clean, first_debit, first_credit = self._validate_rows(rows)

        with self.pe.db.transaction() as tx:
            if mode == "E":
                slno = int(slno or 0)
                if slno <= 0 and vchno:
                    v = tx.scalar("SELECT MAX(slno) FROM daybookpart WHERE TRIM(vchno) = :v",
                                  {"v": vchno.strip().upper()})
                    slno = int(v or 0)
                if slno <= 0:
                    raise JournalError("Edit entry not found")
                if not vchno:
                    vchno = str(tx.scalar("SELECT vchno FROM daybookpart WHERE slno = :s LIMIT 1",
                                          {"s": slno}) or "").strip()
                tx.execute("DELETE FROM daybook WHERE slno = :s", {"s": slno})
                tx.execute("DELETE FROM daybookpart WHERE slno = :s", {"s": slno})
            else:
                slno = self.pe.next_serial_no(tx)
                if self.control == 1:
                    vchno = "JLB/" + str(self.pe.increment_gen_int(tx, "VCHNOJB")).rjust(5, "0")
                else:
                    vchno = "JLE/" + str(self.pe.increment_gen_int(tx, "VCHNOJE")).rjust(5, "0")

            narration = (narration or "").strip() or f"Journal entry no: {vchno}"
            narration = narration[:100]

            lines = self.build_lines(slno, tdate, clean, first_debit, first_credit)
            assert zero_sum(lines) == Decimal("0.00"), "journal not balanced"
            for line in lines:
                self.pe.insert_daybook_line(tx, line)
            self.pe.insert_daybookpart(tx, {
                "slno": slno, "vchno": vchno, "particular": narration, "tdate": tdate,
                "ic": "", "uid": (self.session.user_code if self.session else ""),
            })

        log_delpart(self.pe.db, self.session, f"Journal({vchno}) {'Updated' if mode == 'E' else 'Added'}",
                    utype="E" if mode == "E" else "A", ttype="R")
        return {"slno": slno, "vchno": vchno, "message": "Saved"}

    def delete(self, slno: int) -> str:
        slno = int(slno or 0)
        if slno <= 0:
            raise JournalError("Invalid slno")
        with self.pe.db.transaction() as tx:
            self.pe.delete_voucher(tx, slno)
        log_delpart(self.pe.db, self.session, f"Journal(slno {slno}) Deleted", utype="D", ttype="R")
        return "Deleted"
