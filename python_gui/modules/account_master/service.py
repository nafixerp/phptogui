"""Account Master business rules — port of AccountMasterController.

Ports saveAccountInternal / validateAccount / deleteAccountInternal / load and
the opening-balance sign convention. Money uses Decimal.

Sign convention (docs/accounting-posting-logic.md): debit opening balance is
stored NEGATIVE, credit POSITIVE. Active column = opbal at gilevel 1 else opbalb.

Delete guards: reserved accounts, party-linked accounts (actype2 ∈ C/S/G/R/J),
and accounts with daybook transactions cannot be deleted here. Code cannot be
changed once daybook transactions exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import to_decimal
from .repo import AccountMasterRepo

VALID_ACTYPE1 = ("R", "E", "A", "L")
PARTY_TYPES = ("C", "S", "G", "R", "J")


class AccountError(Exception):
    pass


@dataclass
class AccountForm:
    data: dict = field(default_factory=dict)

    def get(self, key, default=""):
        return self.data.get(key, default)

    def flag(self, key) -> bool:
        # request->input(key) truthiness (checkbox present/non-empty)
        return self.data.get(key) not in (None, "", False, 0, "0")


def _trim_upper(v) -> str:
    return str(v or "").strip().upper()


def normalize_amount(raw, balance_type: str) -> Decimal:
    """Port of normalizeAmount(): abs, debit -> negative, else positive."""
    amount = (to_decimal(raw) or Decimal("0")).copy_abs()
    res = -amount if str(balance_type or "debit").strip().lower() == "debit" else amount
    return Decimal("0") if res == 0 else res


class AccountMasterService:
    def __init__(self, repo: AccountMasterRepo, session: AppSession | None = None, gilevel: int = 1):
        self.repo = repo
        self.session = session
        self.gilevel = int(getattr(session, "gilevel", gilevel) or 1)

    def opening_column(self) -> str:
        return "opbal" if self.gilevel == 1 else "opbalb"

    # -- reads --------------------------------------------------------------
    def list(self, search: str = "") -> list[dict]:
        return self.repo.list_accounts(search.strip())

    def list_groups(self, search: str = "") -> list[dict]:
        return self.repo.list_groups(search.strip())

    def list_bs_heads(self) -> list[dict]:
        return self.repo.list_bs_heads()

    def load(self, accode: str) -> dict | None:
        """Map an accountm row to the form payload (apiAccount 'load')."""
        row = self.repo.load_account(accode)
        if not row:
            return None
        accode_u = _trim_upper(accode)
        col = self.opening_column()
        opening = to_decimal(row.get(col, row.get("opbal", 0))) or Decimal("0")
        a1 = _trim_upper(row.get("actype1", "A"))
        a2 = _trim_upper(row.get("actype2", ""))
        return {
            "accode": accode_u,
            "desc": str(row.get("name") or ""),
            "grcode": str(row.get("grcode") or ""),
            "bshead": str(row.get("bshead") or ""),
            "balance": opening.copy_abs(),
            "pos": str(row.get("tplpos") or ""),
            "shedpos": str(row.get("shepos") or ""),
            "shedgrp": str(row.get("shedgrp") or accode_u),
            "note": str(row.get("note") or ""),
            "debit_checked": opening <= 0,
            "cash_checked": a2 == "H",
            "bank_checked": a2 == "B",
            "revenue_checked": a1 == "R",
            "expense_checked": a1 == "E",
            "asset_checked": (_trim_upper(row.get("actype1", "A")) or "A") == "A",
            "liability_checked": a1 == "L",
            "display_checked": int(row.get("control") or 1) != 2,
            "hlp_checked": int(row.get("hlp") or 1) == 0,
            "sp_checked": int(row.get("sp") or 0) == 1,
            "reserve_checked": _trim_upper(row.get("reserve", "N")) == "Y",
            "removed_checked": int(row.get("removed") or 0) == 1,
            "blocked_checked": _trim_upper(row.get("blocked", "N")) == "Y",
        }

    # -- validation ---------------------------------------------------------
    def validate(self, accode: str, mode: str) -> None:
        """Port of validateAccount(); raises AccountError on failure."""
        accode = _trim_upper(accode)
        mode = str(mode or "").strip().upper()
        if accode == "":
            raise AccountError("Account code is required")
        exists = self.repo.account_exists(accode)
        if mode == "A" and exists:
            raise AccountError("This account code already exists")
        if mode in ("E", "D") and not exists:
            raise AccountError("This account code does not exist")
        if mode == "D":
            meta = self.repo.account_meta(accode)
            if meta and _trim_upper(meta.get("reserve", "N")) == "Y":
                raise AccountError("Reserved code. Cannot delete.")
            if meta and _trim_upper(meta.get("actype2", "")) in PARTY_TYPES:
                raise AccountError("Linked account. Cannot delete through Account Master.")
            if self.repo.daybook_amount_total(accode) > 0:
                raise AccountError("Transactions exist. Cannot delete.")

    # -- commands -----------------------------------------------------------
    def save(self, form: AccountForm) -> str:
        """Port of saveAccountInternal(). Returns success message; raises AccountError."""
        mode = str(form.get("mode", "A")).strip().upper() or "A"
        accode = _trim_upper(form.get("accode"))
        original = _trim_upper(form.get("original_accode", accode))
        desc = str(form.get("desc") or "").strip()
        grcode = _trim_upper(form.get("grcode"))
        bshead = _trim_upper(form.get("bshead"))
        actype1 = _trim_upper(form.get("actype1", "A"))
        actype2 = _trim_upper(form.get("actype2")) or " "

        if accode == "":
            raise AccountError("Account code is required")
        if desc == "":
            raise AccountError("Description is required")
        if grcode == "":
            raise AccountError("Group is compulsory for all accounts")
        if bshead == "" and actype1 in ("A", "L"):
            raise AccountError("BS Head is compulsory for Asset/Liability type accounts")
        if actype1 not in VALID_ACTYPE1:
            raise AccountError("Invalid account type")

        if mode == "E":
            if self.session is not None and self.session.is_blocked("MASTEREDIT"):
                raise AccountError("You are not permitted to edit entries")
            if original == "":
                raise AccountError("Original account code is required for edit")
            if not self.repo.account_exists(original):
                raise AccountError("This account code does not exist")
            if accode != original:
                if self.repo.account_exists(accode):
                    raise AccountError("This account code already exists")
                if self.repo.daybook_count(original) > 0:
                    raise AccountError("Cannot change code. Transactions exist for this account.")
        else:
            self.validate(accode, mode)

        opening = normalize_amount(form.get("balance", 0), str(form.get("balance_type", "debit")).lower())
        col = self.opening_column()
        shedgrp = _trim_upper(form.get("shedgrp")) or accode

        row = {
            "accode": accode, "name": desc,
            "actype1": actype1, "actype2": actype2,
            "control": 1 if form.flag("display") else 2,
            "grcode": grcode, "hlp": 0 if form.flag("hlp") else 1,
            "tplpos": str(form.get("pos") or "").strip(),
            "bshead": bshead,
            "shepos": str(form.get("shedpos") or "").strip(),
            "shedgrp": shedgrp,
            "reserve": "Y" if form.flag("reserve") else "N",
            "sp": 1 if form.flag("sp") else 0,
            "removed": 1 if form.flag("removed") else 0,
            "blocked": "Y" if form.flag("blocked") else "N",
            "note": str(form.get("note") or "").strip(),
        }
        if self.repo.has_column("accountm", col):
            row[col] = opening
        else:
            row["opbal"] = opening
            row["opbalb"] = opening

        filtered = self.repo.filter_columns("accountm", row)
        if not filtered:
            raise AccountError("No writable columns found in accountm")

        with self.repo.db.transaction() as tx:
            if mode == "A":
                self.repo.insert_account(tx, filtered)
            else:
                self.repo.update_account(tx, original, filtered)
                if accode != original and self.repo.has_column("accountm", "shedgrp"):
                    self.repo.update_shedgrp_refs(tx, original, accode)

        action = "Added" if mode == "A" else "Updated"
        log_delpart(self.repo.db, self.session, f"Account({accode}) {action}",
                    utype="A" if mode == "A" else "E", ttype="M")
        return "Account saved successfully"

    def delete(self, accode: str) -> str:
        """Port of deleteAccountInternal()."""
        self.validate(accode, "D")
        with self.repo.db.transaction() as tx:
            deleted = self.repo.delete_account(tx, accode)
        if deleted == 0:
            raise AccountError("Delete did not remove any row.")
        log_delpart(self.repo.db, self.session, f"Account({_trim_upper(accode)}) Deleted",
                    utype="D", ttype="M")
        return "Account deleted successfully"
