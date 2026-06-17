"""StockTypeService logic tests (headless, no DB).

Verifies the validation rules and the destroy decision tree match
StockTypeController, using an in-memory fake repository.
"""

import pytest

from python_gui.modules.stocktype.service import (
    ConfirmRequired,
    DeleteBlocked,
    StockTypeForm,
    StockTypeService,
    ValidationError,
)


class _FakeDb:
    # log_delpart() probes this; returning False makes auditing a no-op.
    def table_exists(self, _name):
        return False


class FakeRepo:
    def __init__(self, rows=None, usage=None):
        self.db = _FakeDb()
        self.rows = {r["code"]: dict(r) for r in (rows or [])}
        self._usage = usage or {"total": 0, "itemsonly": 0}
        self.calls = []

    def table_exists(self):
        return True

    def list(self):
        return list(self.rows.values())

    def get_by_code(self, code):
        return self.rows.get(code.strip().upper())

    def code_exists(self, code):
        return code.strip().upper() in self.rows

    def get_default(self):
        return next((r for r in self.rows.values() if r.get("def")), None)

    def create(self, code, name, def_, compare, make_default):
        self.calls.append(("create", code, name, def_, compare, make_default))
        self.rows[code] = {"code": code, "name": name, "def": def_, "compare": compare}

    def save(self, code, name, def_, compare, make_default):
        self.calls.append(("save", code, name, def_, compare, make_default))
        self.rows[code] = {"code": code, "name": name, "def": def_, "compare": compare}

    def usage(self, code):
        return dict(self._usage)

    def delete_with_items(self, code):
        self.calls.append(("delete_with_items", code))
        self.rows.pop(code.strip().upper(), None)


def svc(rows=None, usage=None):
    return StockTypeService(FakeRepo(rows, usage))


# -- validation --------------------------------------------------------------

@pytest.mark.parametrize("code,name,msg", [
    ("", "Gold", "code is required"),
    ("ABCDEFGHIJK", "Gold", "exceed 10"),     # 11 chars
    ("G", "", "name is required"),
    ("G", "x" * 31, "exceed 30"),
])
def test_create_validation(code, name, msg):
    with pytest.raises(ValidationError) as e:
        svc().create(StockTypeForm(code=code, name=name))
    assert msg in str(e.value)


def test_create_duplicate_code():
    s = svc(rows=[{"code": "G", "name": "Gold", "def": 0, "compare": 0}])
    with pytest.raises(ValidationError, match="already exists"):
        s.create(StockTypeForm(code="g", name="Gold2"))


def test_create_normalizes_and_sets_default():
    s = svc()
    s.create(StockTypeForm(code=" g ", name="  Gold  ", def_=True, compare=False))
    assert s.repo.calls[0] == ("create", "G", "Gold", 1, 0, True)


def test_update_not_found():
    with pytest.raises(ValidationError, match="not found"):
        svc().update("X", StockTypeForm(code="X", name="Y"))


def test_update_persists():
    s = svc(rows=[{"code": "G", "name": "Gold", "def": 0, "compare": 0}])
    s.update("g", StockTypeForm(code="g", name="Gold Bars", def_=False, compare=True))
    assert ("save", "G", "Gold Bars", 0, 1, False) in s.repo.calls


# -- destroy decision tree ---------------------------------------------------

def test_delete_when_unused():
    s = svc(rows=[{"code": "G", "name": "Gold", "def": 0, "compare": 0}],
            usage={"total": 0, "itemsonly": 0})
    s.delete("G")
    assert ("delete_with_items", "G") in s.repo.calls


def test_delete_items_only_requires_confirm():
    s = svc(rows=[{"code": "G", "name": "Gold", "def": 0, "compare": 0}],
            usage={"total": 5, "itemsonly": 5})
    with pytest.raises(ConfirmRequired):
        s.delete("G")
    assert not any(c[0] == "delete_with_items" for c in s.repo.calls)


def test_delete_used_in_transactions_blocked():
    s = svc(rows=[{"code": "G", "name": "Gold", "def": 0, "compare": 0}],
            usage={"total": 5, "itemsonly": 2})
    with pytest.raises(DeleteBlocked):
        s.delete("G")


def test_force_delete_overrides_usage():
    s = svc(rows=[{"code": "G", "name": "Gold", "def": 0, "compare": 0}],
            usage={"total": 5, "itemsonly": 5})
    s.delete("G", force=True)
    assert ("delete_with_items", "G") in s.repo.calls
