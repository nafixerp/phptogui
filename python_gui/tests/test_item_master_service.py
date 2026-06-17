"""ItemMasterService tests — payload transforms, save add/edit, delete guards."""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.item_master.repo import ItemMasterRepo
from python_gui.modules.item_master.service import ItemMasterError, ItemMasterService

sqlite3.register_adapter(Decimal, str)

_ITEMS_COLS = {
    "code", "name", "regionalname", "grpcode", "subgrpcode", "itype", "wastage",
    "mcharge", "vaperc", "touch", "rate", "stktouch", "ornament", "taxable",
    "reserve", "disabled", "bccompulsory", "defstktype", "defquality", "qtype",
    "showinstkrep", "qty", "weight", "opqty", "opweight",
}


def make_service():
    db = Database()
    db._engine = create_engine("sqlite://", future=True)
    cols = ", ".join(f"{c} TEXT" for c in sorted(_ITEMS_COLS))
    with db._engine.begin() as c:
        c.execute(text(f"CREATE TABLE items ({cols}, PRIMARY KEY (code))"))
    repo = ItemMasterRepo(db)
    repo.columns = lambda t="items": _ITEMS_COLS
    repo.filter_columns = lambda row, t="items": {k: v for k, v in row.items() if k.lower() in _ITEMS_COLS}
    repo.has_table = lambda t="items": t == "items"
    repo.has_column = lambda t, c: (c in _ITEMS_COLS) if t == "items" else False
    repo.transaction_weight = lambda code: 0.0
    return ItemMasterService(repo), repo


def test_save_validation():
    svc, _ = make_service()
    with pytest.raises(ItemMasterError, match="Code is required"):
        svc.save({"code": "", "desc": "x"}, "add")
    with pytest.raises(ItemMasterError, match="Description is required"):
        svc.save({"code": "R1", "desc": ""}, "add")
    with pytest.raises(ItemMasterError, match="maximum length is 10"):
        svc.save({"code": "ABCDEFGHIJK", "desc": "x"}, "add")


def test_add_transforms_and_zero_cols():
    svc, repo = make_service()
    svc.save({"code": "ring1", "desc": "gold ring", "itype": "G", "ornament": True,
              "reserve": False, "wastage": "8.5", "qtype": "22K"}, "add")
    row = repo.get("RING1")
    assert row["code"] == "RING1" and row["name"] == "GOLD RING"   # upper
    assert row["ornament"] == "Y" and row["reserve"] == " "        # YN / RES
    assert row["defquality"] == "22K" and row["qtype"] == "22K"    # qtype -> 2 cols
    assert str(row["weight"]) == "0"                               # add zero-col


def test_add_duplicate_blocked():
    svc, _ = make_service()
    svc.save({"code": "R1", "desc": "x"}, "add")
    with pytest.raises(ItemMasterError, match="already exists"):
        svc.save({"code": "R1", "desc": "y"}, "add")


def test_edit_only_updates_supplied_columns():
    svc, repo = make_service()
    svc.save({"code": "R1", "desc": "Ring", "vaperc": "10", "rate": "5000"}, "add")
    # edit supplies only desc -> rate/vaperc must be preserved
    svc.save({"code": "R1", "desc": "Ring Updated"}, "edit")
    row = repo.get("R1")
    assert row["name"] == "RING UPDATED"
    assert str(row["rate"]) == "5000" and str(row["vaperc"]) == "10"


def test_edit_missing_item():
    svc, _ = make_service()
    with pytest.raises(ItemMasterError, match="does not exist"):
        svc.save({"code": "GHOST", "desc": "x"}, "edit")


def test_delete_reserved_blocked():
    svc, repo = make_service()
    svc.save({"code": "R1", "desc": "x", "reserve": True}, "add")
    with pytest.raises(ItemMasterError, match="reserved"):
        svc.delete("R1")


def test_delete_blocked_when_transaction_weight():
    svc, repo = make_service()
    svc.save({"code": "R1", "desc": "x"}, "add")
    repo.transaction_weight = lambda code: 12.5
    with pytest.raises(ItemMasterError, match="Some entries exist"):
        svc.delete("R1")


def test_delete_ok_when_clean():
    svc, repo = make_service()
    svc.save({"code": "R1", "desc": "x"}, "add")
    assert "deleted" in svc.delete("R1").lower()
    assert repo.get("R1") is None
