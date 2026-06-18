"""Kuri / Scheme Collection — port of KuriCollectionController::save.

Each collection row books the amount into the scheme account and the cash/bank
account: scheme `code` +amount (opaccode = cash), cash -amount (opaccode = code)
=> balances to zero. A `kuricolln` row records the collection; a refund is a
negative amount. Weight is derived (amount / gold_rate) only when the scheme is
flagged showwgtdet. slno from the shared SERIALNO counter.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import money, weight
from ...core.posting import PostingEngine, zero_sum


class KuriError(Exception):
    pass


class KuriCollectionService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def _kuricolln_cols(self) -> set[str]:
        return set(self.pe.db.columns("kuricolln")) if self.pe.db.table_exists("kuricolln") else set()

    def collect(self, rows: list[dict], date: str, cash_account: str = "CASH",
                gold_rate: str | float = 0, note: str = "", label: str = "Scheme") -> dict:
        date = str(date or "").strip()
        if date == "":
            raise KuriError("Valid date required")
        if not rows:
            raise KuriError("No rows to save")
        cash_ac = str(cash_account or "CASH").strip().upper() or "CASH"
        grate = money(gold_rate)
        kcols = self._kuricolln_cols()
        saved = []

        with self.pe.db.transaction() as tx:
            for index, r in enumerate(rows, 1):
                code = str(r.get("code") or "").strip().upper()
                amount = money(r.get("amount", 0))
                if code == "" or abs(amount) < Decimal("0.0001"):
                    continue
                slno = self.pe.next_serial_no(tx)
                vchno = self.pe.reserve_voucher(tx, "VRB/" if self.control == 1 else "VRE/",
                                                "VCHNORB" if self.control == 1 else "VCHNORE")
                show_wgt = str(r.get("showwgt") or "N").strip().upper() == "Y"
                wgt = weight(amount / grate) if (show_wgt and grate > 0) else weight(0)

                if kcols:
                    krow = {"slno": slno, "tdate": date, "code": code, "amount": amount,
                            "control": self.control, "sno": index, "grate": grate,
                            "agent": str(r.get("agent") or "").strip().upper(),
                            "rcptno": str(r.get("rcptno") or "").strip(), "closed": "N",
                            "wgt": wgt, "docno": vchno, "note": note}
                    krow = {k: v for k, v in krow.items() if k.lower() in kcols}
                    names = ", ".join(krow); binds = ", ".join(f":{k}" for k in krow)
                    tx.execute(f"INSERT INTO kuricolln ({names}) VALUES ({binds})", krow)

                lines = [
                    {"slno": slno, "tdate": date, "accode": code, "amount": amount,
                     "control": self.control, "opaccode": cash_ac, "sno": index},
                    {"slno": slno, "tdate": date, "accode": cash_ac, "amount": money(-amount),
                     "control": self.control, "opaccode": code, "sno": index},
                ]
                assert zero_sum(lines) == Decimal("0.00")
                for ln in lines:
                    self.pe.insert_daybook_line(tx, ln)
                if self.pe.db.table_exists("daybookpart"):
                    kind = "Refund" if amount < 0 else "Colln"
                    part = f"By {label} {kind} - {vchno}"
                    if krow_rcpt := str(r.get("rcptno") or "").strip():
                        part += f" - RN:{krow_rcpt}"
                    self.pe.insert_daybookpart(tx, {
                        "slno": slno, "vchno": vchno, "particular": part[:100],
                        "staff": str(r.get("agent") or "").strip().upper(),
                        "tdate": date, "control": self.control,
                    })
                saved.append({"slno": slno, "code": code, "vchno": vchno, "amount": str(amount)})

        if not saved:
            raise KuriError("No valid rows to save")
        log_delpart(self.pe.db, self.session, f"{label} Collection ({len(saved)} rows)", utype="A", ttype="R")
        return {"saved": len(saved), "rows": saved}
