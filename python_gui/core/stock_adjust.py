"""Shared item stock adjuster — port of the adjustItemStock() helper used by
the refinery / repair / order-sale posting paths.

Applies signed deltas to ``items`` (and ``itemsstk`` per stock-type): the
"b" balances (``weightb``/``qtyb``/``stonewgtb``) are always moved; the live
balances (``weight``/``qty``/``stonewgt``) move only at control level 1. Every
column is guarded so a frozen schema missing a column is skipped. Writes go
through the active transaction.
"""

from __future__ import annotations

from .db import Database, Tx


def _deltas(cols: set[str], qd, wd, sd, control: int) -> dict:
    upd: dict[str, str] = {}
    if "qtyb" in cols:
        upd["qtyb"] = "COALESCE(qtyb,0) + :qd"
    if "weightb" in cols:
        upd["weightb"] = "COALESCE(weightb,0) + :wd"
    if "stonewgtb" in cols and sd != 0:
        upd["stonewgtb"] = "COALESCE(stonewgtb,0) + :sd"
    if control == 1:
        if "qty" in cols:
            upd["qty"] = "COALESCE(qty,0) + :qd"
        if "weight" in cols:
            upd["weight"] = "COALESCE(weight,0) + :wd"
        if "stonewgt" in cols and sd != 0:
            upd["stonewgt"] = "COALESCE(stonewgt,0) + :sd"
    return upd


def adjust_item_stock(db: Database, tx: Tx, code: str, qty_delta, weight_delta,
                      stone_delta, stktype: str, control: int) -> None:
    code = str(code).strip()
    if not code or not db.table_exists("items"):
        return
    params = {"qd": qty_delta, "wd": weight_delta, "sd": stone_delta, "c": code}
    icols = set(db.columns("items"))
    upd = _deltas(icols, qty_delta, weight_delta, stone_delta, control)
    if upd:
        sets = ", ".join(f"{k} = {v}" for k, v in upd.items())
        tx.execute(f"UPDATE items SET {sets} WHERE TRIM(code) = :c", params)

    stktype = str(stktype or "").strip()
    if not stktype or not db.table_exists("itemsstk"):
        return
    scols = set(db.columns("itemsstk"))
    if "code" not in scols or "stktype" not in scols:
        return
    exists = tx.fetchall(
        "SELECT 1 FROM itemsstk WHERE TRIM(code) = :c AND stktype = :st LIMIT 1",
        {"c": code, "st": stktype})
    if not exists:
        tx.execute("INSERT INTO itemsstk (code, stktype) VALUES (:c, :st)", {"c": code, "st": stktype})
    upd = _deltas(scols, qty_delta, weight_delta, stone_delta, control)
    if upd:
        sets = ", ".join(f"{k} = {v}" for k, v in upd.items())
        tx.execute(f"UPDATE itemsstk SET {sets} WHERE TRIM(code) = :c AND stktype = :st",
                   {**params, "st": stktype})
