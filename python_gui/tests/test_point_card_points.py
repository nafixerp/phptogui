"""Pending: point card points report."""

import sqlite3
from decimal import Decimal

from sqlalchemy import create_engine, text

from python_gui.core.db import Database
from python_gui.modules.point_card_points.service import PointCardPointsService

sqlite3.register_adapter(Decimal, str)


def make_db():
    db = Database(); db._engine = create_engine("sqlite://", future=True)
    with db._engine.begin() as c:
        c.execute(text("CREATE TABLE clients (code TEXT, name TEXT, pcard TEXT, oppcardpoints NUM)"))
        c.execute(text("CREATE TABLE pcard (code TEXT, name TEXT)"))
        c.execute(text("CREATE TABLE pcardtable (pcard TEXT, isubgrp TEXT, pointbasedon TEXT, valuefor1point NUM, valueperpoint NUM, minsalesamt NUM, rounddown INT)"))
        c.execute(text("CREATE TABLE salesm (slno INT, custcode TEXT, tdate TEXT, control INT, redmpoints NUM)"))
        c.execute(text("CREATE TABLE salesd (slno INT, code TEXT, weight NUM, amount NUM)"))
        c.execute(text("CREATE TABLE items (code TEXT, subgrpcode TEXT)"))
        c.execute(text("INSERT INTO clients VALUES ('C1','ACME','GOLD',5)"))
        c.execute(text("INSERT INTO pcard VALUES ('GOLD','Gold Card')"))
        # 1 point per 1000 amount, value 2 per point, no rounddown, all subgroups ('')
        c.execute(text("INSERT INTO pcardtable VALUES ('GOLD','','A',1000,2,0,0)"))
        c.execute(text("INSERT INTO salesm VALUES (1,'C1','2026-06-10',1,3)"))  # redeemed 3
        c.execute(text("INSERT INTO salesd VALUES (1,'R1',10.0,50000)"))
        c.execute(text("INSERT INTO items VALUES ('R1','RING')"))
    db.table_exists = lambda t: t in {"clients", "pcard", "pcardtable", "salesm", "salesd", "items"}
    db.column_exists = lambda t, c: True
    db.columns = lambda t: set()
    return db


def test_point_card_points_calc():
    res = PointCardPointsService(make_db()).report("2026-06-01", "2026-06-30")
    assert len(res["rows"]) == 1
    r = res["rows"][0]
    assert r["samt"] == Decimal("50000.00")
    # points = 50000 / 1000 = 50
    assert r["spoints"] == Decimal("50.00")
    # point value = 50 * 2 = 100
    assert r["pointvalue"] == Decimal("100.00")
    # closing = opening 5 + earned 50 - redeemed 3 = 52
    assert r["clpoints"] == Decimal("52.00")
    assert r["pcardname"] == "Gold Card"
