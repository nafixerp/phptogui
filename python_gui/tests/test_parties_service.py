"""PartiesService tests (headless).

Covers the ported pure helpers (date/address/sign), code generation, the
buildClientRow / accountm row builders, and the save validation + flow, using
an in-memory fake repository.
"""

from decimal import Decimal

import pytest

from python_gui.modules.parties.service import (
    PartiesService,
    PartyError,
    PartyForm,
    normalize_address_lines,
    normalize_date,
)


# -- pure helpers ------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("2024-01-31", "2024-01-31"),
    ("31/01/2024", "2024-01-31"),
    ("31-01-2024", "2024-01-31"),
    ("1/2/2020", None),        # not zero-padded -> rejected (round-trip)
    ("", None),
    ("garbage", None),
    ("2024-13-01", None),      # invalid month
])
def test_normalize_date(value, expected):
    assert normalize_date(value) == expected


def test_address_short_lines_passthrough():
    assert normalize_address_lines("12 Main St", "Apt 4", "") == ["12 Main St", "Apt 4", ""]


def test_address_long_rewraps_to_30():
    long1 = "A" * 40
    out = normalize_address_lines(long1, "", "")
    assert all(len(x) <= 30 for x in out) and len(out) == 3


# -- fakes -------------------------------------------------------------------

class _Tx:
    def __init__(self, store):
        self.store = store

    def execute(self, sql, params=None):
        self.store.append(("sql", sql, params or {}))

    def scalar(self, sql, params=None):
        return None


class _FakeDb:
    def __init__(self):
        self.database = "demo"
        self.ops = []

    def table_exists(self, _name):
        return False  # keep delpart auditing a no-op

    class _Ctx:
        def __init__(self, db):
            self.db = db

        def __enter__(self):
            return _Tx(self.db.ops)

        def __exit__(self, *a):
            return False

    def transaction(self):
        return _FakeDb._Ctx(self)


class FakeRepo:
    """Minimal repo capturing writes and serving configurable reads."""
    def __init__(self, clients=None, counters=None, prefixes=None):
        self.db = _FakeDb()
        self.clients = {c["code"]: dict(c) for c in (clients or [])}
        self.counters = counters or {}
        self.prefixes = prefixes or {}
        self.client_cols = {
            "code", "name", "addr1", "addr2", "addr3", "city", "telephone", "mobile",
            "email", "opbalance", "opbalanceb", "ctype", "control", "removed", "grp",
            "state", "opweight", "opdepwgtbal", "idno",
        }
        self.accountm_cols = {
            "accode", "name", "opbal", "opbalb", "actype1", "actype2", "control",
            "grcode", "bshead", "shedgrp", "hlp", "sp", "removed", "blocked",
        }
        self.inserted = []

    def has_table(self, t):
        return t in ("clients", "accountm")

    def columns(self, t):
        return self.client_cols if t == "clients" else self.accountm_cols if t == "accountm" else set()

    def filter_columns(self, t, row):
        cols = self.columns(t)
        return {k: v for k, v in row.items() if k.lower() in cols}

    def client_exists(self, code):
        return code in self.clients

    def get_client(self, code):
        return self.clients.get(code.strip())

    def get_accountm(self, code):
        return None

    def generali_value(self, code):
        return int(self.counters.get(code, 0))

    def generals_value(self, code):
        return self.prefixes.get(code)

    def set_generali(self, code, value, tx=None):
        self.counters[code] = value

    def max_party_code_number(self, prefix):
        return 0

    def code_has_linked_transactions(self, code):
        return False

    def daybook_has_accode(self, code):
        return False

    def insert_client(self, tx, row):
        self.inserted.append(("client", dict(row)))
        self.clients[row["code"]] = dict(row)

    def update_client(self, tx, code, row):
        self.clients.setdefault(code, {}).update(row)

    def upsert_accountm(self, tx, row):
        self.inserted.append(("accountm", dict(row)))


def svc(**kw):
    return PartiesService(FakeRepo(**kw))


# -- validation --------------------------------------------------------------

def test_save_requires_name():
    with pytest.raises(PartyError, match="Name is required"):
        svc().save(PartyForm({"type": "C", "name": "  "}))


def test_customer_requires_phone_or_mobile():
    with pytest.raises(PartyError, match="Phone or mobile"):
        svc().save(PartyForm({"type": "C", "name": "ACME"}))


def test_supplier_does_not_require_phone():
    s = svc()
    s.save(PartyForm({"type": "S", "name": "Vendor", "code": "S0001"}))
    assert "S0001" in s.repo.clients


# -- sign convention + row build --------------------------------------------

def test_opening_balance_sign_credit_positive_debit_negative():
    s = svc()
    s.save(PartyForm({"type": "S", "name": "V", "code": "S1",
                      "opbalance": "100", "balance_type": "credit"}))
    row = next(r for kind, r in s.repo.inserted if kind == "client")
    assert row["opbalance"] == Decimal("100")

    s2 = svc()
    s2.save(PartyForm({"type": "S", "name": "V", "code": "S2",
                       "opbalance": "100", "balance_type": "debit"}))
    row2 = next(r for kind, r in s2.repo.inserted if kind == "client")
    assert row2["opbalance"] == Decimal("-100")


def test_accountm_row_built_for_customer():
    s = svc()
    # empty grp triggers the default-group fallback (else grcode = clients.grp)
    s.save(PartyForm({"type": "C", "name": "ACME", "code": "C1", "mobile": "999", "grp": ""}))
    ac = next(r for kind, r in s.repo.inserted if kind == "accountm")
    assert ac["accode"] == "C1"
    assert ac["actype1"] == "A"          # customer -> Asset
    assert ac["grcode"] == "SUNDB"       # default debtors group
    assert ac["name"] == "ACME(C1)"


def test_supplier_accountm_is_liability_sundr():
    s = svc()
    s.save(PartyForm({"type": "S", "name": "VEND", "code": "S9", "grp": ""}))
    ac = next(r for kind, r in s.repo.inserted if kind == "accountm")
    assert ac["actype1"] == "L" and ac["grcode"] == "SUNCR"


def test_grp_defaults_to_O_and_flows_to_grcode():
    # No grp provided -> clients.grp = 'O' -> accountm.grcode = 'O' (matches Laravel)
    s = svc()
    s.save(PartyForm({"type": "S", "name": "VEND", "code": "S8"}))
    ac = next(r for kind, r in s.repo.inserted if kind == "accountm")
    assert ac["grcode"] == "O"


def test_depositor_becomes_customer_with_dep_group():
    s = svc()
    s.save(PartyForm({"type": "D", "name": "DEP", "code": "C5", "mobile": "1"}))
    row = next(r for kind, r in s.repo.inserted if kind == "client")
    assert row["ctype"] == "C" and row["grp"] == "DEP"


# -- code generation ---------------------------------------------------------

def test_next_code_uses_clastno_and_prefix():
    s = svc(counters={"CLASTNO": 41}, prefixes={"CPREFIX": "C"})
    assert s.next_code("C") == "C0042"


def test_next_code_supplier_uses_slastno():
    s = svc(counters={"SLASTNO": 7}, prefixes={"SPREFIX": "S"})
    assert s.next_code("S") == "S0008"


def test_reserve_next_code_persists_counter():
    s = svc(counters={"CLASTNO": 41}, prefixes={"CPREFIX": "C"})
    s.save(PartyForm({"type": "C", "name": "ACME", "mobile": "999"}))  # empty code -> reserve
    assert s.repo.counters["CLASTNO"] == 42
    assert "C0042" in s.repo.clients
