"""Phase 2 master service tests (headless) — group, subgroup, purity, counters,
denomination, mctable, bill prefix, app settings.

Uses a real in-memory SQLite engine (with a Decimal adapter) wired into Database,
plus stubbed catalog helpers where modules probe information_schema.
"""

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from python_gui.core.db import Database

sqlite3.register_adapter(Decimal, str)


def make_db(ddl: list[str]) -> Database:
    db = Database()
    db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        for stmt in ddl:
            c.execute(text(stmt))
    return db


# -- Item Group --------------------------------------------------------------

def test_item_group_crud():
    from python_gui.modules.item_group.repo import ItemGroupRepo
    from python_gui.modules.item_group.service import ItemGroupError, ItemGroupForm, ItemGroupService

    db = make_db(["CREATE TABLE itemgrp (code TEXT PRIMARY KEY, name TEXT, mname TEXT, itype TEXT, orn TEXT, pos INT, showinstkrep TEXT)"])
    repo = ItemGroupRepo(db)
    repo.items_in_group = lambda code: 0   # no items table
    svc = ItemGroupService(repo)
    svc.save(ItemGroupForm(code="ring", name="Rings", type="X", ornament=True), "A")
    row = repo.get("RING")
    assert row["itype"] == "G"          # invalid type coerced to G
    assert row["orn"] == "Y" and row["name"] == "Rings"
    with pytest.raises(ItemGroupError, match="already exists"):
        svc.save(ItemGroupForm(code="RING", name="x"), "A")
    svc.save(ItemGroupForm(code="RING", name="Gold Rings", type="S"), "E")
    assert repo.get("RING")["name"] == "Gold Rings"
    assert "deleted" in svc.delete("RING").lower()
    assert repo.get("RING") is None


# -- Item Sub-Group ----------------------------------------------------------

def test_subgroup_upsert_and_delete():
    from python_gui.modules.item_subgroup.repo import ItemSubGroupRepo
    from python_gui.modules.item_subgroup.service import ItemSubGroupService

    db = make_db(["CREATE TABLE itemsubgrp (code TEXT, name TEXT)"])
    repo = ItemSubGroupRepo(db)
    repo.used_in_barcode = lambda code: 0
    svc = ItemSubGroupService(repo)
    svc.save("sg1", "Sub One")
    svc.save("sg1", "Sub One Updated")        # upsert
    rows = svc.list()
    assert len(rows) == 1 and rows[0]["name"] == "Sub One Updated"
    svc.delete("SG1")
    assert svc.list() == []


# -- Purity Type -------------------------------------------------------------

def test_purity_save_rename_and_delete():
    from python_gui.modules.purity_type.repo import PurityTypeRepo
    from python_gui.modules.purity_type.service import PurityTypeService, normalize_touch

    assert normalize_touch("91,6") == Decimal("91.6")
    assert normalize_touch("9a1.6.7") == Decimal("91.67")

    db = make_db(["CREATE TABLE itemsqtype (code TEXT, touch NUM)"])
    repo = PurityTypeRepo(db)
    repo.cascade_rename = lambda tx, o, n: None   # no related tables here
    repo.usage_count = lambda code: 0
    svc = PurityTypeService(repo)
    svc.save_row("22K", "91.6")
    assert repo.get("22K")["touch"] in ("91.6", 91.6)
    svc.save_row("22KT", "91.6", original_code="22K")    # rename
    assert repo.get("22K") is None and repo.exists("22KT")
    svc.delete("22KT")
    assert not repo.exists("22KT")


# -- Counters ----------------------------------------------------------------

def test_counters_save_seeds_generali():
    from python_gui.modules.counters.repo import CountersRepo
    from python_gui.modules.counters.service import CountersService

    db = make_db([
        "CREATE TABLE counter (code TEXT PRIMARY KEY, name TEXT, startbillno NUM)",
        "CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)",
    ])
    repo = CountersRepo(db)
    repo.has_table = lambda t="counter": t in ("counter", "generali")
    repo.has_generali = lambda: True
    repo.sales_count = lambda code: 0   # no salesm -> treat as zero sales
    repo.used_in_barcode = lambda code: False
    svc = CountersService(repo)
    svc.save("C1", "Counter 1", 500)
    assert repo.list()[0]["startbillno"] in (500, "500")
    assert int(db.scalar("SELECT cvalue FROM generali WHERE code='C1'")) == 500


# -- Denomination ------------------------------------------------------------

def test_denomination_upsert():
    from python_gui.modules.denomination.repo import DenominationRepo
    from python_gui.modules.denomination.service import DenominationService

    db = make_db(["CREATE TABLE denom_master (code TEXT PRIMARY KEY, name TEXT, cvalue NUM)"])
    svc = DenominationService(DenominationRepo(db))
    svc.save("d500", "500 Note", "500.00")
    svc.save("d500", "Five Hundred", "500")
    rows = svc.list()
    assert len(rows) == 1 and rows[0]["name"] == "Five Hundred"
    svc.delete("D500")
    assert svc.list() == []


# -- MC Table ----------------------------------------------------------------

def test_mctable_bulk_replace_skips_zero_rows():
    from python_gui.modules.mctable.repo import MCTableRepo
    from python_gui.modules.mctable.service import MCTableService

    db = make_db(["CREATE TABLE mctable (code TEXT, weight1 NUM, weight2 NUM, mc NUM, mcpergm NUM, mcperqty NUM, vaperc NUM, iqtype TEXT)"])
    svc = MCTableService(MCTableRepo(db))
    msg = svc.save("RING01", "22K", [
        {"weight1": "0", "weight2": "10", "mc": "100", "vaperc": "8"},
        {"weight1": "0", "weight2": "0", "mc": "0"},      # skipped (both weights 0)
    ])
    rows = svc.get_for_item("RING01", "22K")
    assert len(rows) == 1 and "1 slab" in msg
    # re-save replaces (not appends)
    svc.save("RING01", "22K", [{"weight1": "10", "weight2": "20", "mc": "120"}])
    assert len(svc.get_for_item("RING01", "22K")) == 1


# -- Bill Prefix -------------------------------------------------------------

def test_bill_prefix_save_seeds_counters():
    from python_gui.modules.bill_prefix.repo import BillPrefixRepo
    from python_gui.modules.bill_prefix.service import BillPrefixService

    db = make_db([
        "CREATE TABLE salestype (code TEXT PRIMARY KEY, name TEXT, prefix TEXT, startno INT, formno TEXT, taxperc NUM, pprefix TEXT, pstartno INT, srprefix TEXT, srstartno INT, prprefix TEXT, prstartno INT)",
        "CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)",
    ])
    repo = BillPrefixRepo(db)
    repo.has_table = lambda t: t in ("salestype", "generali")
    repo.has_column = lambda t, c: True
    svc = BillPrefixService(repo)
    svc.save_row({"code": "GST", "name": "GST Sales", "prefix": "GS", "startno": "100",
                  "srprefix": "SR", "srstartno": "10", "pprefix": "PU", "pstartno": "5",
                  "prprefix": "PR", "prstartno": "2", "taxperc": "3", "formno": "F1"})
    assert int(db.scalar("SELECT cvalue FROM generali WHERE code='SALESGS'")) == 100
    assert int(db.scalar("SELECT cvalue FROM generali WHERE code='PURCHPU'")) == 5
    data = svc.retrieve()
    assert data[0]["code"] == "GST" and data[0]["startno"] == 100


# -- App Settings ------------------------------------------------------------

def test_app_settings_roundtrip():
    from python_gui.modules.app_settings.repo import AppSettingsRepo
    from python_gui.modules.app_settings.service import AppSettingsService

    db = make_db([
        "CREATE TABLE generals (code TEXT PRIMARY KEY, cvalue TEXT)",
        "CREATE TABLE generali (code TEXT PRIMARY KEY, cvalue NUM)",
    ])
    repo = AppSettingsRepo(db)
    repo.has_generals = lambda: True
    svc = AppSettingsService(repo)
    svc.save({"name": "My Shop", "address": "Main St", "phone": "123",
              "clastno": "50", "slastno": "20", "sbpref": "BC", "sblen": "6"})
    data = svc.load()
    assert data["name"] == "My Shop" and data["clastno"] == "50" and data["sbpref"] == "BC"
    # blank counter is ignored
    svc.save({"name": "My Shop 2", "address": "", "phone": "", "clastno": ""})
    assert svc.load()["clastno"] == "50"      # unchanged
