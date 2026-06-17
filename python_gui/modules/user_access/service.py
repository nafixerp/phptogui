"""User Access business rules — port of UserAccessController.

Manages userm + userd. Passwords are stored via the legacy fp-crypt
(core.crypto.pcode_value) so users created/edited here log in through the same
NativeAuthController path. Money/percent limits use Decimal.

Validation (StoreUserAccessRequest): mode add|edit; code required, ≤10,
[A-Z0-9]+ (uppercased); name required ≤30 (uppercased); password ≤50 (required
on add); numeric limits ≥ 0.

Delete guards: ADMIN and MGR are protected. Delete removes userd, userhist and
the userm row (and user_company_access if present).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.crypto import pcode_value
from ...core.decimals import to_decimal
from .repo import UserAccessRepo

_NUMERIC_FIELDS = ["maxcredit", "maxdisc", "maxdiscperc", "minvaperc", "maxadjwgtbc"]
_PROTECTED = ("ADMIN", "MGR")
_CODE_RE = re.compile(r"^[A-Z0-9]+$")


class UserAccessError(Exception):
    pass


@dataclass
class UserAccessForm:
    code: str = ""
    name: str = ""
    password: str = ""
    permissions: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    maxcredit: object = 0
    maxdisc: object = 0
    maxdiscperc: object = 0
    minvaperc: object = 0
    maxadjwgtbc: object = 0


class UserAccessService:
    def __init__(self, repo: UserAccessRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    # -- reads --------------------------------------------------------------
    def list_users(self) -> list[dict]:
        return self.repo.list_users()

    def get_user(self, code: str) -> dict | None:
        return self.repo.get_user(code)

    def permissions_for(self, code: str) -> list[str]:
        return self.repo.permission_list(code)

    # -- validation ---------------------------------------------------------
    def _validate(self, form: UserAccessForm, mode: str) -> tuple[str, str]:
        if mode not in ("add", "edit"):
            raise UserAccessError("Invalid mode")
        code = (form.code or "").strip().upper()
        name = (form.name or "").strip().upper()
        if code == "":
            raise UserAccessError("User code is required")
        if len(code) > 10 or not _CODE_RE.match(code):
            raise UserAccessError("Code must be up to 10 letters/digits (A-Z, 0-9)")
        if name == "":
            raise UserAccessError("Name is required")
        if len(name) > 30:
            raise UserAccessError("Name cannot exceed 30 characters")
        if len(form.password or "") > 50:
            raise UserAccessError("Password cannot exceed 50 characters")
        for f in _NUMERIC_FIELDS:
            v = to_decimal(getattr(form, f, 0))
            if v is None or v < 0:
                raise UserAccessError(f"{f} must be a number ≥ 0")
        return code, name

    # -- commands -----------------------------------------------------------
    def save(self, form: UserAccessForm, mode: str) -> str:
        """Port of saveUser(). Returns a success message; raises on error."""
        code, name = self._validate(form, mode)
        password = form.password or ""

        if mode == "add" and password == "":
            raise UserAccessError("Password is required for new user")
        if mode == "add" and self.repo.user_exists(code):
            raise UserAccessError("User code already exists")
        if mode == "edit" and not self.repo.user_exists(code):
            raise UserAccessError("User not found")

        payload = {"name": name}
        for f in _NUMERIC_FIELDS:
            payload[f] = to_decimal(getattr(form, f, 0)) or Decimal("0")

        with self.repo.db.transaction() as tx:
            if mode == "add":
                payload["code"] = code
                payload["pcode"] = pcode_value(password)
                self.repo.insert_user(tx, payload)
            else:
                if password != "":
                    payload["pcode"] = pcode_value(password)
                self.repo.update_user(tx, code, payload)
            self.repo.sync_permissions(tx, code, form.permissions or [])

        log_delpart(self.repo.db, self.session,
                    f"User Access({code}) {'Added' if mode == 'add' else 'Updated'}",
                    utype="A" if mode == "add" else "E", ttype="R")
        return "User saved successfully"

    def delete(self, code: str) -> str:
        """Port of deleteUser()."""
        code = (code or "").strip().upper()
        if code == "":
            raise UserAccessError("User code required")
        if code in _PROTECTED:
            raise UserAccessError("Cannot delete protected user")
        if not self.repo.user_exists(code):
            raise UserAccessError("User not found")
        with self.repo.db.transaction() as tx:
            self.repo.delete_user(tx, code)
        log_delpart(self.repo.db, self.session, f"User Access({code}) Deleted", utype="D", ttype="R")
        return "User deleted"
