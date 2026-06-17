"""Bill Prefix rules — port of BillPrefixController retrieve/save (per-row).

retrieve() returns each salestype row with effective (auto-healed) counters.
save_row() upserts one salestype row and seeds the four generali counters
(SALES/SRET/PURCH/PRET). Field text is fitted to the controller's FIELD_LIMITS.

NOTE: the controller's bulk save also deletes salestype codes absent from the
submitted set (unless used in salesm). The desktop saves incrementally per row,
so that bulk stale-delete is intentionally not performed here (safer). Documented
in docs/phase1-2-remaining.md.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import to_decimal
from .repo import BillPrefixRepo

FIELD_LIMITS = {"code": 10, "name": 30, "formno": 20, "prefix": 20,
                "pprefix": 20, "srprefix": 20, "prprefix": 20}


class BillPrefixError(Exception):
    pass


def _fit(value: str, limit: int) -> str:
    return str(value or "").strip()[:limit]


class BillPrefixService:
    def __init__(self, repo: BillPrefixRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    def retrieve(self) -> list[dict]:
        out = []
        for r in self.repo.list_salestype():
            prefix = str(r.get("prefix") or "").strip()
            srprefix = str(r.get("srprefix") or "").strip()
            pprefix = str(r.get("pprefix") or "").strip()
            prprefix = str(r.get("prprefix") or "").strip()
            out.append({
                "code": str(r.get("code") or ""), "name": str(r.get("name") or ""),
                "taxperc": r.get("taxperc") or 0, "formno": str(r.get("formno") or ""),
                "prefix": prefix,
                "startno": self.repo.resolve_effective_counter("SALES" + prefix, prefix, "salesm", "billno", int(r.get("startno") or 0)),
                "srprefix": srprefix,
                "srstartno": self.repo.resolve_effective_counter("SRET" + srprefix, srprefix, "salesrm", "billno", int(r.get("srstartno") or 0)),
                "pprefix": pprefix,
                "pstartno": self.repo.resolve_effective_counter("PURCH" + pprefix, pprefix, "purchasem", "billno", int(r.get("pstartno") or 0)),
                "prprefix": prprefix,
                "prstartno": self.repo.resolve_effective_counter("PRET" + prprefix, prprefix, "purchaserm", "billno", int(r.get("prstartno") or 0)),
            })
        return out

    def save_row(self, data: dict) -> str:
        code = _fit(str(data.get("code", "")).upper(), FIELD_LIMITS["code"])
        if code == "":
            raise BillPrefixError("Code is required.")
        # length validation against FIELD_LIMITS (pre-fit), matching the controller
        for field, limit in FIELD_LIMITS.items():
            if len(str(data.get(field) or "").strip()) > limit:
                raise BillPrefixError(f"{field.upper()} max {limit} characters.")

        def up(field):
            return _fit(str(data.get(field, "")).upper(), FIELD_LIMITS.get(field, 20))

        def num(field):
            return int(to_decimal(data.get(field, 0)) or 0)

        row = {
            "code": code, "name": up("name"), "taxperc": to_decimal(data.get("taxperc", 0)) or Decimal("0"),
            "formno": up("formno"), "prefix": up("prefix"), "startno": num("startno"),
            "srprefix": up("srprefix"), "srstartno": num("srstartno"),
            "pprefix": up("pprefix"), "pstartno": num("pstartno"),
            "prprefix": up("prprefix"), "prstartno": num("prstartno"),
        }
        with self.repo.db.transaction() as tx:
            self.repo.upsert_salestype(tx, row)
            self.repo.upsert_generali("SALES" + row["prefix"], row["startno"], tx)
            self.repo.upsert_generali("SRET" + row["srprefix"], row["srstartno"], tx)
            self.repo.upsert_generali("PURCH" + row["pprefix"], row["pstartno"], tx)
            self.repo.upsert_generali("PRET" + row["prprefix"], row["prstartno"], tx)
        log_delpart(self.repo.db, self.session, "Bill Prefix Settings Saved", utype="E", ttype="R")
        return "Saved successfully"
