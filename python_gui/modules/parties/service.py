"""Parties business rules — port of NativeCustomerController.

Covers the create/edit/delete flow for every party type stored in `clients`
(C/S/F/D/G/R/J). Money & weight use Decimal. All string casing/trim/length and
the debit/credit sign convention are reproduced from buildClientRow();
upsertAccountM() builds the matching `accountm` row.

Deferred (auxiliary, flagged): CSV import, photo upload (clientspict),
clientsgs goldsmith weights (G/R/J only), and background secondary-DB sync.
These are not part of the core clients/accountm save and are documented in
docs/phase3-module-map.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import to_decimal
from .repo import PartiesRepo

VALID_TYPES = ("C", "S", "F", "D", "G", "R", "J")

TYPE_INFO = {
    "C": ("Customer", "Customers"),
    "S": ("Supplier", "Suppliers"),
    "F": ("Staff", "Staff"),
    "D": ("Depositor", "Depositors"),
    "G": ("Goldsmith", "Goldsmiths"),
    "R": ("Refiner", "Refiners"),
    "J": ("Jewellery", "Jewellery"),
}


class PartyError(Exception):
    """User-facing validation/flow error (mirrors the controller's JSON errors)."""


# ---------------------------------------------------------------------------
# Pure helpers (ported one-to-one)
# ---------------------------------------------------------------------------

def _upper(value, length: int = 0) -> str:
    s = str(value or "").strip().upper()
    return s[:length] if length > 0 else s


def _signed(value, type_str: str) -> Decimal:
    """debit/credit sign convention from buildClientRow: credit=+abs else -abs."""
    d = to_decimal(value) or Decimal("0")
    a = d.copy_abs()
    res = a if str(type_str or "debit").strip().lower() == "credit" else -a
    return Decimal("0") if res == 0 else res


def normalize_date(value) -> str | None:
    """Port of normalizeDate(): accept Y-m-d, d/m/Y, d-m-Y; else None."""
    text = str(value or "").strip()
    if text == "":
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if dt.strftime(fmt) == text:   # round-trip check (rejects '1/2/2020')
            return dt.strftime("%Y-%m-%d")
    return None


def normalize_address_lines(addr1: str, addr2: str = "", addr3: str = "") -> list[str]:
    """Port of normalizeAddressLines(): keep 3 lines, re-wrap to <=30 chars."""
    limit = 30
    lines = [str(addr1 or "").strip(), str(addr2 or "").strip(), str(addr3 or "").strip()]
    if all(len(x) <= limit for x in lines):
        return lines

    combined = " ".join(x for x in lines if x != "").strip()
    if combined == "":
        return ["", "", ""]

    chunks: list[str] = []
    while combined != "" and len(chunks) < 3:
        if len(combined) <= limit:
            chunks.append(combined)
            break
        sl = combined[:limit + 1]
        break_at = sl.rfind(" ")
        if break_at == -1 or break_at < 10:
            break_at = limit
        chunks.append(combined[:break_at].strip())
        combined = combined[break_at:].lstrip()

    while len(chunks) < 3:
        chunks.append("")
    return [chunks[0][:limit], chunks[1][:limit], chunks[2][:limit]]


@dataclass
class PartyForm:
    """Flat payload mirroring the form fields the controller reads."""
    data: dict = field(default_factory=dict)

    def get(self, key, default=""):
        return self.data.get(key, default)

    def has(self, key) -> bool:
        # isset()-style: present and truthy-ish (checkboxes send the field when on)
        return key in self.data and self.data[key] not in (None, "", False, 0, "0")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PartiesService:
    def __init__(self, repo: PartiesRepo, session: AppSession | None = None,
                 prefix_overrides: dict | None = None):
        self.repo = repo
        self.session = session
        self.prefix_overrides = prefix_overrides or {}

    # -- type helpers -------------------------------------------------------
    @staticmethod
    def normalize_type(t: str) -> str:
        t = str(t or "").strip().upper()
        return t if t in VALID_TYPES else "C"

    @staticmethod
    def type_title(t: str) -> str:
        return TYPE_INFO.get(t, TYPE_INFO["C"])[0]

    def list(self, ctype: str, search: str = "", no_removed: bool = True) -> list[dict]:
        return self.repo.list_by_type(self.normalize_type(ctype), search.strip(), no_removed)

    def get(self, code: str) -> dict | None:
        code = str(code or "").strip()
        row = self.repo.get_client(code)
        if not row:
            return None
        data = dict(row)
        ac = self.repo.get_accountm(code)
        if ac:
            data["acgrp"] = ac.get("grcode")
            data["bshead"] = ac.get("bshead")
            data["ac_blocked"] = ac.get("blocked")
        return data

    # -- code generation ----------------------------------------------------
    def resolve_prefix(self, ctype: str) -> str:
        """Port of resolvePartyCodePrefix()."""
        t = ctype.strip().upper()
        if t not in VALID_TYPES:
            t = "C"
        fallback = "C" if t == "D" else (t if t != "" else "S")
        prefix_code = {"C": "CPREFIX", "D": "CPREFIX", "S": "SPREFIX"}.get(t, "")
        prefix = fallback
        if prefix_code:
            val = self.repo.generals_value(prefix_code)
            prefix = (val if val is not None else fallback).strip() or fallback
        # optional per-company override (storage/app/company-code-prefixes.json)
        db_key = (self.repo.db.database or "").strip().lower()
        override = str(self.prefix_overrides.get(db_key, {}).get(t, "")).strip()
        if override:
            prefix = override.upper()
        return (prefix or fallback).upper()

    def next_code(self, ctype: str) -> str:
        """Port of getNextAutoCode() — suggestion only, does not touch counters."""
        t = self.normalize_type(ctype)
        is_dep = t == "D"
        base = "C" if is_dep else t
        if base == "C":
            last_no = self.repo.generali_value("CLASTNO")
            prefix = self.resolve_prefix("C")
        else:
            last_no = self.repo.generali_value("SLASTNO")
            prefix = self.resolve_prefix(base)
        if prefix == "":
            prefix = base
        if is_dep:
            prefix = "C"
        derived = self.repo.max_party_code_number(prefix)
        last_no = max(last_no, derived)
        return prefix + str(last_no + 1).rjust(4, "0")

    def _reserve_next_code(self, ctype: str) -> str:
        """Port of reserveNextCode() — reserves + persists the counter."""
        counter = "CLASTNO" if ctype == "C" else "SLASTNO"
        prefix = self.resolve_prefix(ctype)
        with self.repo.db.transaction() as tx:
            current = self.repo.generali_value(counter)
            current = max(current, self.repo.max_party_code_number(prefix))
            nxt = current + 1
            self.repo.set_generali(counter, nxt, tx)
        return (prefix + str(nxt).rjust(4, "0")).upper()

    def _sync_code_counter(self, tx, code: str, ctype: str) -> None:
        """Port of syncCodeCounter() — bump counter to a manually-entered number."""
        if ctype not in ("C", "S", "F"):
            return
        prefix = self.resolve_prefix(ctype).upper()
        upper_code = code.strip().upper()
        if prefix == "" or not upper_code.startswith(prefix):
            return
        suffix = upper_code[len(prefix):]
        if suffix == "" or not suffix.isdigit():
            return
        counter = "CLASTNO" if ctype == "C" else "SLASTNO"
        current = self.repo.generali_value(counter)
        self.repo.set_generali(counter, max(current, int(suffix)), tx)

    # -- row builders -------------------------------------------------------
    def build_client_row(self, data: PartyForm, code: str, ctype: str) -> dict:
        """Port of buildClientRow() + column filtering to the clients schema."""
        addr1, addr2, addr3 = normalize_address_lines(
            data.get("addr1"), data.get("addr2"), data.get("addr3")
        )
        row = {
            "code": code,
            "name": _upper(data.get("name"), 40),
            "addr1": _upper(addr1), "addr2": _upper(addr2), "addr3": _upper(addr3),
            "city": _upper(data.get("city")),
            "telephone": str(data.get("telephone") or "").strip(),
            "mobile": str(data.get("mobile") or "").strip(),
            "email": str(data.get("email") or "").strip(),
            "pin": _upper(data.get("pin")), "state": _upper(data.get("state")),
            "panadhar": _upper(data.get("panadhar")), "tin": _upper(data.get("tin")),
            "cst": _upper(data.get("cst")),
            "opbalance": _signed(data.get("opbalance", 0), data.get("balance_type", "debit")),
            "opbalanceb": _signed(data.get("opbalanceb", 0), data.get("balance_type_b", "debit")),
            "ctype": ctype, "control": 1,
            "removed": 1 if data.has("removed") else 0,
            "blocked": "Y" if data.has("blocked") else "N",
            "salary": to_decimal(data.get("salary", 0)),
            "cocode": _upper(data.get("cocode")),
            "grp": _upper(data.get("grp", "O")),
            "route": _upper(data.get("route")),
            "carea": _upper(data.get("carea", data.get("area", ""))),
            "adate": normalize_date(data.get("adate")),
            "duedate": normalize_date(data.get("duedate")),
            "cutrate": to_decimal(data.get("cutrate", 0)),
            "colncomn": to_decimal(data.get("colncomn", 0)),
            "opweight": _signed(data.get("opweight", 0), data.get("weight_type", "debit")),
            "opdepwgtbal": _signed(data.get("opdepwgtbal", 0), data.get("depweight_type", "debit")),
            "idno": _upper(data.get("idno")), "religion": _upper(data.get("religion")),
            "note": _upper(data.get("note")),
            "coparty": "Y" if data.has("coparty") else "N",
            "pcard": _upper(data.get("pcard")), "smcode": _upper(data.get("smcode")),
            "pospwd": str(data.get("pospwd") or "").strip(),
            "agent": "Y" if data.has("agent") else "N",
            "oppcardpoints": to_decimal(data.get("oppcardpoints", 0)),
            "pcardno": _upper(data.get("pcardno")),
            "approval": "Y" if data.has("approval") else "N",
            "homemobile": str(data.get("homemobile") or "").strip(),
            "distance": int(to_decimal(data.get("distance", 0)) or 0),
            "billdate": normalize_date(data.get("billdate")),
        }
        return self.repo.filter_columns("clients", row)

    def build_accountm_row(self, client_row: dict, data: PartyForm) -> dict:
        """Port of upsertAccountM()'s row build (column-filtered)."""
        code = str(client_row["code"])
        name = (f"{client_row.get('name', '')}({code})")[:30]
        ctype = str(client_row.get("ctype", "C")).upper()
        actype1 = "A" if ctype == "C" else "L"
        default_group = "SUNDB" if ctype in ("C", "D", "J") else "SUNCR"
        grcode = str(data.get("acgrp", client_row.get("grp", default_group)) or "").strip() or default_group
        bshead = str(data.get("bshead", grcode) or "").strip() or default_group
        row = {
            "accode": code, "name": name,
            "opbal": client_row.get("opbalance", Decimal("0")),
            "opbalb": client_row.get("opbalanceb", Decimal("0")),
            "actype1": actype1, "actype2": ctype,
            "control": int(client_row.get("control", 1)),
            "grcode": grcode, "bshead": bshead, "shedgrp": bshead,
            "hlp": 1, "sp": 0,
            "removed": int(client_row.get("removed", 0)),
            "blocked": str(client_row.get("blocked", "N")),
        }
        return self.repo.filter_columns("accountm", row)

    # -- commands -----------------------------------------------------------
    def save(self, form: PartyForm) -> dict:
        """Port of save() — validation, code reserve, upsert clients + accountm."""
        code = _upper(form.get("code"))
        original_code = _upper(form.get("original_code", code))
        ctype = self.normalize_type(form.get("type", form.get("ctype", "C")))

        if str(form.get("name") or "").strip() == "":
            raise PartyError("Name is required")
        if ctype in ("C", "D") and str(form.get("telephone") or "").strip() == "" \
                and str(form.get("mobile") or "").strip() == "":
            raise PartyError("Phone or mobile number is required")

        is_depositor = ctype == "D"
        if is_depositor:
            ctype = "C"
            form.data["grp"] = "DEP"

        if code == "":
            code = self._reserve_next_code(ctype)
            form.data["code"] = code
            if original_code == "":
                original_code = code

        is_rename = original_code != "" and original_code != code
        if is_rename:
            if not self.repo.client_exists(original_code):
                raise PartyError("Original code not found")
            if self.repo.client_exists(code):
                raise PartyError("New code already exists")
            if self.repo.code_has_linked_transactions(original_code):
                raise PartyError("This code already has linked transactions. Rename is blocked for safety.")

        exists = self.repo.client_exists(code)
        client_row = self.build_client_row(form, code, ctype)
        accountm_row = self.build_accountm_row(client_row, form)

        with self.repo.db.transaction() as tx:
            if is_rename:
                self.repo.rename_code(tx, original_code, code)
                exists = True
            if exists:
                self.repo.update_client(tx, code, client_row)
            else:
                self.repo.insert_client(tx, client_row)
                self._sync_code_counter(tx, code, ctype)
            if self.repo.has_table("accountm"):
                self.repo.upsert_accountm(tx, accountm_row)

        label = self.type_title("D" if is_depositor else ctype)
        action = "Renamed" if is_rename else ("Updated" if exists else "Added")
        log_delpart(self.repo.db, self.session, f"{label}({code}) {action}",
                    utype="E" if exists else "A", ttype="R")
        return self.get(code) or {}

    def delete(self, code: str) -> None:
        """Port of delete() — blocked if daybook entries reference the code."""
        code = str(code or "").strip()
        if code == "":
            raise PartyError("Code is required")
        if self.repo.daybook_has_accode(code):
            raise PartyError("Transactions exist. Cannot delete this code.")
        with self.repo.db.transaction() as tx:
            self.repo.delete_client(tx, code)
        log_delpart(self.repo.db, self.session, f"Customer({code}) Deleted", utype="D", ttype="R")
