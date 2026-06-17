"""AccountMasterService tests (headless).

Verifies the opening-balance sign convention, save validation, the edit/rename
and delete guards, and the load->form mapping, using a fake repository.
"""

from decimal import Decimal

import pytest

from python_gui.modules.account_master.service import (
    AccountError,
    AccountForm,
    AccountMasterService,
    normalize_amount,
)


# -- sign convention ---------------------------------------------------------

def test_normalize_amount_debit_negative_credit_positive():
    assert normalize_amount("100", "debit") == Decimal("-100")
    assert normalize_amount("100", "credit") == Decimal("100")
    assert normalize_amount("-100", "credit") == Decimal("100")  # abs first
    assert normalize_amount("0", "debit") == Decimal("0")


# -- fakes -------------------------------------------------------------------

class _Tx:
    def __init__(self, store):
        self.store = store

    def execute(self, sql, params=None):
        self.store.append((sql, params or {}))

        class _R:
            rowcount = 1
        return _R()

    def scalar(self, sql, params=None):
        return None


class _FakeDb:
    def __init__(self):
        self.database = "demo"
        self.writes = []

    def table_exists(self, _n):
        return False

    class _Ctx:
        def __init__(self, db):
            self.db = db

        def __enter__(self):
            return _Tx(self.db.writes)

        def __exit__(self, *a):
            return False

    def transaction(self):
        return _FakeDb._Ctx(self)


class FakeRepo:
    def __init__(self, accounts=None, tx_totals=None):
        self.db = _FakeDb()
        self.accounts = {a["accode"]: dict(a) for a in (accounts or [])}
        self.tx_totals = tx_totals or {}
        self.cols = {
            "accode", "name", "actype1", "actype2", "control", "grcode", "hlp",
            "tplpos", "bshead", "shepos", "shedgrp", "reserve", "sp", "removed",
            "blocked", "note", "opbal", "opbalb",
        }
        self.inserted = []
        self.updated = []

    def has_table(self, t):
        return t in ("accountm", "daybook")

    def has_column(self, t, c):
        return c in self.cols if t == "accountm" else True

    def columns(self, t):
        return self.cols if t == "accountm" else set()

    def filter_columns(self, t, row):
        return {k: v for k, v in row.items() if k.lower() in self.columns(t)}

    def account_exists(self, code):
        return code.strip().upper() in self.accounts

    def account_meta(self, code):
        return self.accounts.get(code.strip().upper())

    def load_account(self, code):
        return self.accounts.get(code.strip().upper())

    def daybook_amount_total(self, code):
        return float(self.tx_totals.get(code.strip().upper(), 0))

    def daybook_count(self, code):
        return int(self.tx_totals.get(code.strip().upper(), 0))

    def insert_account(self, tx, row):
        self.inserted.append(dict(row))
        self.accounts[row["accode"]] = dict(row)

    def update_account(self, tx, where_code, row):
        self.updated.append((where_code, dict(row)))

    def update_shedgrp_refs(self, tx, old, new):
        self.updated.append(("shedgrp", old, new))

    def delete_account(self, tx, code):
        return 1 if self.accounts.pop(code.strip().upper(), None) else 0


def svc(**kw):
    return AccountMasterService(FakeRepo(**kw))


def base_form(**over):
    d = {"mode": "A", "accode": "EXP01", "desc": "Office Rent",
         "grcode": "INDIR", "actype1": "E", "balance": "0", "balance_type": "debit"}
    d.update(over)
    return AccountForm(d)


# -- validation --------------------------------------------------------------

def test_save_requires_code_desc_group():
    with pytest.raises(AccountError, match="code is required"):
        svc().save(base_form(accode=""))
    with pytest.raises(AccountError, match="Description is required"):
        svc().save(base_form(desc=""))
    with pytest.raises(AccountError, match="Group is compulsory"):
        svc().save(base_form(grcode=""))


def test_asset_requires_bs_head():
    with pytest.raises(AccountError, match="BS Head is compulsory"):
        svc().save(base_form(actype1="A", bshead=""))


def test_invalid_actype():
    with pytest.raises(AccountError, match="Invalid account type"):
        svc().save(base_form(actype1="X"))


def test_duplicate_on_add():
    s = svc(accounts=[{"accode": "EXP01", "name": "x"}])
    with pytest.raises(AccountError, match="already exists"):
        s.save(base_form(accode="EXP01"))


def test_add_persists_with_signed_opening():
    s = svc()
    s.save(base_form(accode="EXP01", balance="500", balance_type="debit"))
    row = s.repo.inserted[0]
    assert row["accode"] == "EXP01" and row["actype1"] == "E"
    assert row["opbal"] == Decimal("-500")        # debit -> negative
    assert row["shedgrp"] == "EXP01"              # defaults to accode


def test_asset_with_bshead_credit_opening():
    s = svc()
    s.save(base_form(accode="BANK1", actype1="A", bshead="CA", balance="1000", balance_type="credit"))
    assert s.repo.inserted[0]["opbal"] == Decimal("1000")


# -- edit / rename guards ----------------------------------------------------

def test_edit_rename_blocked_when_transactions_exist():
    s = svc(accounts=[{"accode": "EXP01", "name": "x"}], tx_totals={"EXP01": 3})
    with pytest.raises(AccountError, match="Transactions exist"):
        s.save(base_form(mode="E", accode="EXP02", original_accode="EXP01"))


def test_edit_rename_blocked_when_new_code_taken():
    s = svc(accounts=[{"accode": "EXP01", "name": "x"}, {"accode": "EXP02", "name": "y"}])
    with pytest.raises(AccountError, match="already exists"):
        s.save(base_form(mode="E", accode="EXP02", original_accode="EXP01"))


def test_edit_rename_updates_shedgrp_refs():
    s = svc(accounts=[{"accode": "EXP01", "name": "x"}])
    s.save(base_form(mode="E", accode="EXP09", original_accode="EXP01"))
    assert any(u[0] == "shedgrp" for u in s.repo.updated)


# -- delete guards -----------------------------------------------------------

def test_delete_reserved_blocked():
    s = svc(accounts=[{"accode": "CASH", "reserve": "Y", "actype2": "H"}])
    with pytest.raises(AccountError, match="Reserved"):
        s.delete("CASH")


def test_delete_party_linked_blocked():
    s = svc(accounts=[{"accode": "C0001", "reserve": "N", "actype2": "C"}])
    with pytest.raises(AccountError, match="Linked account"):
        s.delete("C0001")


def test_delete_with_transactions_blocked():
    s = svc(accounts=[{"accode": "EXP01", "reserve": "N", "actype2": " "}], tx_totals={"EXP01": 5})
    with pytest.raises(AccountError, match="Transactions exist"):
        s.delete("EXP01")


def test_delete_ok_when_clean():
    s = svc(accounts=[{"accode": "EXP01", "reserve": "N", "actype2": " "}])
    assert "deleted" in s.delete("EXP01").lower()
    assert "EXP01" not in s.repo.accounts
