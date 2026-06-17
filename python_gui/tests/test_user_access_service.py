"""UserAccessService tests (headless) — validation, password, perms, delete guards."""

import pytest

from python_gui.core.crypto import pcode_value
from python_gui.modules.user_access.service import (
    UserAccessError,
    UserAccessForm,
    UserAccessService,
)


class _Tx:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append((sql.split()[0].upper(), params or {}))

        class _R:
            rowcount = 1
        return _R()

    def scalar(self, sql, params=None):
        return None


class _FakeDb:
    def __init__(self):
        self.log = []

    def table_exists(self, _n):
        return False

    class _Ctx:
        def __init__(self, db):
            self.db = db

        def __enter__(self):
            return _Tx(self.db.log)

        def __exit__(self, *a):
            return False

    def transaction(self):
        return _FakeDb._Ctx(self)


class FakeRepo:
    def __init__(self, users=None, perms=None):
        self.db = _FakeDb()
        self.users = {u.upper() for u in (users or [])}
        self.perms = perms or {}
        self.inserted = []
        self.updated = []
        self.synced = []

    def has_table(self, _t):
        return False

    def list_users(self):
        return [{"code": c, "name": c} for c in sorted(self.users)]

    def get_user(self, code):
        c = code.strip().upper()
        return {"code": c, "name": c} if c in self.users else None

    def user_exists(self, code):
        return code.strip().upper() in self.users

    def permission_list(self, code):
        return self.perms.get(code.strip().upper(), [])

    def insert_user(self, tx, payload):
        self.inserted.append(dict(payload))
        self.users.add(payload["code"].upper())

    def update_user(self, tx, code, payload):
        self.updated.append((code.upper(), dict(payload)))

    def sync_permissions(self, tx, code, items):
        self.synced.append((code.upper(), list(items)))

    def delete_user(self, tx, code):
        self.users.discard(code.strip().upper())


def svc(**kw):
    return UserAccessService(FakeRepo(**kw))


def form(**over):
    base = dict(code="OPR1", name="Operator", password="secret", permissions=[])
    base.update(over)
    return UserAccessForm(**base)


# -- validation --------------------------------------------------------------

@pytest.mark.parametrize("code", ["", "TOOLONGCODE1", "bad code", "OP-1"])
def test_invalid_codes(code):
    with pytest.raises(UserAccessError):
        svc().save(form(code=code), "add")


def test_name_required():
    with pytest.raises(UserAccessError, match="Name is required"):
        svc().save(form(name=""), "add")


def test_password_required_on_add():
    with pytest.raises(UserAccessError, match="Password is required"):
        svc().save(form(password=""), "add")


def test_duplicate_on_add():
    with pytest.raises(UserAccessError, match="already exists"):
        svc(users=["OPR1"]).save(form(code="OPR1"), "add")


def test_negative_limit_rejected():
    with pytest.raises(UserAccessError, match="maxcredit"):
        svc().save(form(maxcredit="-5"), "add")


# -- add / edit --------------------------------------------------------------

def test_add_stores_legacy_pcode_and_perms():
    s = svc()
    s.save(form(code="opr1", name="operator", password="secret",
                permissions=["MDI_SALES_BILL", "readonly", ""]), "add")
    row = s.repo.inserted[0]
    assert row["code"] == "OPR1" and row["name"] == "OPERATOR"
    assert row["pcode"] == pcode_value("secret")          # legacy fp-crypt value
    # menuitems normalised + empties dropped happens in repo.sync_permissions;
    # service passes them through as-is:
    assert s.repo.synced[0][0] == "OPR1"


def test_edit_keeps_password_when_blank():
    s = svc(users=["OPR1"])
    s.save(form(code="OPR1", name="Op", password=""), "edit")
    _, payload = s.repo.updated[0]
    assert "pcode" not in payload          # blank password -> unchanged
    assert payload["name"] == "OP"


def test_edit_sets_password_when_given():
    s = svc(users=["OPR1"])
    s.save(form(code="OPR1", name="Op", password="newpass"), "edit")
    _, payload = s.repo.updated[0]
    assert payload["pcode"] == pcode_value("newpass")


def test_edit_missing_user():
    with pytest.raises(UserAccessError, match="not found"):
        svc().save(form(code="GHOST"), "edit")


# -- delete guards -----------------------------------------------------------

@pytest.mark.parametrize("code", ["ADMIN", "MGR"])
def test_protected_users_cannot_be_deleted(code):
    with pytest.raises(UserAccessError, match="protected"):
        svc(users=[code]).delete(code)


def test_delete_missing_user():
    with pytest.raises(UserAccessError, match="not found"):
        svc().delete("GHOST")


def test_delete_ok():
    s = svc(users=["OPR1"])
    assert "deleted" in s.delete("OPR1").lower()
    assert "OPR1" not in s.repo.users
