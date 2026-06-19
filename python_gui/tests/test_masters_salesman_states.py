"""Masters: salesman (sman) + states (state/statestate) grid CRUD."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.salesman_master.service import SalesmanError, SalesmanMasterService
from python_gui.modules.states_master.service import StatesError, StatesMasterService

sqlite3.register_adapter(Decimal, str)


def _bind(db, colmap):
    db.table_exists = lambda t: t in colmap
    db.column_exists = lambda t, c: c in colmap.get(t, set())
    db.columns = lambda t: colmap.get(t, set())


# ---- salesman master ------------------------------------------------------

_SM = {
    "sman": {"code", "name", "accode", "active"},
    "accountm": {"accode", "name"},
    "orderm": {"slno", "smcode"},
}


def make_sm_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE sman (code TEXT, name TEXT, accode TEXT, active TEXT)"))
        c.execute(text("CREATE TABLE accountm (accode TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE orderm (slno INT, smcode TEXT)"))
        c.execute(text("INSERT INTO accountm VALUES ('A1','Salary')"))
        c.execute(text("INSERT INTO sman VALUES ('S1','OLD','A1','Y')"))
        c.execute(text("INSERT INTO orderm VALUES (1,'S2')"))
    _bind(db, _SM)
    return db


def test_salesman_save_all_replaces_and_validates():
    db = make_sm_db(); svc = SalesmanMasterService(db)
    msg = svc.save_all([
        {"code": "s2", "name": "ravi", "accode": "A1", "active": "y"},
        {"code": "s3", "name": "kumar", "accode": "", "active": "n"},
        {"code": "", "name": "skip", "accode": "", "active": "Y"},  # blank code dropped
    ])
    assert "saved" in msg.lower()
    rows = {r["code"]: r for r in svc.list()}
    # old S1 gone (full replace), S2/S3 inserted, codes+names upper-cased
    assert set(rows) == {"S2", "S3"}
    assert rows["S2"]["name"] == "RAVI" and rows["S2"]["active"] == "Y"
    assert rows["S3"]["active"] == "N" and rows["S3"]["accode"] == ""


def test_salesman_save_all_rejects_bad_account():
    db = make_sm_db(); svc = SalesmanMasterService(db)
    with pytest.raises(SalesmanError):
        svc.save_all([{"code": "S9", "name": "X", "accode": "NOPE", "active": "Y"}])
    # transaction rolled back -> original S1 still present
    assert {r["code"] for r in svc.list()} == {"S1"}


def test_salesman_delete_usage_guard():
    db = make_sm_db(); svc = SalesmanMasterService(db)
    svc.save_all([{"code": "S2", "name": "RAVI", "accode": "A1", "active": "Y"}])
    # S2 is used by orderm.smcode -> blocked
    with pytest.raises(SalesmanError):
        svc.delete("S2")
    assert {r["code"] for r in svc.list()} == {"S2"}


def test_salesman_delete_ok_when_unused():
    db = make_sm_db(); svc = SalesmanMasterService(db)
    svc.save_all([{"code": "S5", "name": "FREE", "accode": "", "active": "Y"}])
    assert svc.delete("S5") == "Deleted."
    assert svc.list() == []


def test_salesman_account_list():
    svc = SalesmanMasterService(make_sm_db())
    accts = svc.account_list()
    assert accts == [{"code": "A1", "name": "Salary"}]


# ---- states master --------------------------------------------------------

def _states_colmap(state_cols):
    return {"state": state_cols, "salesm": {"slno", "statecode"}}


def make_states_db(name_separate=True):
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    cols = {"code", "name"} if name_separate else {"code"}
    with db._engine.begin() as c:
        if name_separate:
            c.execute(text("CREATE TABLE state (code TEXT, name TEXT)"))
            c.execute(text("INSERT INTO state VALUES ('29','Karnataka')"))
        else:
            c.execute(text("CREATE TABLE state (state TEXT)"))
        c.execute(text("CREATE TABLE salesm (slno INT, statecode TEXT)"))
        c.execute(text("INSERT INTO salesm VALUES (1,'29')"))
    _bind(db, _states_colmap(cols if name_separate else {"state"}))
    return db


def test_states_resolve_and_save_upsert():
    db = make_states_db(); svc = StatesMasterService(db)
    res = svc.save_all([
        {"code": "29", "name": "Karnataka State"},  # update existing
        {"code": "32", "name": "Kerala"},            # insert new
        {"code": "", "name": "skip"},                # dropped
    ])
    assert res["inserted"] == 1 and res["updated"] == 1
    rows = {r["code"]: r["name"] for r in svc.list()}
    assert rows == {"29": "Karnataka State", "32": "Kerala"}


def test_states_delete_usage_guard():
    db = make_states_db(); svc = StatesMasterService(db)
    # state 29 referenced by salesm.statecode -> blocked
    with pytest.raises(StatesError):
        svc.delete("29")
    # an unused state can be deleted
    svc.save_all([{"code": "32", "name": "Kerala"}])
    assert svc.delete("32") == "State deleted successfully"
    assert {r["code"] for r in svc.list()} == {"29"}


def test_states_check_usage():
    svc = StatesMasterService(make_states_db())
    assert svc.check_usage("29") == {"count": 1, "in_use": True}
    assert svc.check_usage("99") == {"count": 0, "in_use": False}


def test_states_no_table():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    _bind(db, {})
    svc = StatesMasterService(db)
    assert svc.list() == []
    with pytest.raises(StatesError):
        svc.save_all([{"code": "1", "name": "X"}])
