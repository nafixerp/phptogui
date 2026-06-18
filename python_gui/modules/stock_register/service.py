"""Stock Register (read-only) — port of StockRegisterController core.

Per item: opening (itemsstk) + purchases - sales + sales-returns - purchase-
returns over the date range (master control <= rlevel) => closing qty/weight.
Movement detail tables join their master (salesm/purchasem/...) for tdate+control.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money

# detail table -> (master table, master key, sign)
_MOVES = [
    ("purchased", "purchasem", +1), ("salesd", "salesm", -1),
    ("salesrd", "salesrm", +1), ("purchaserd", "purchaserm", -1),
]


class StockRegisterService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = int(rlevel or 1)

    def _opening(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        if not self.db.table_exists("itemsstk"):
            return out
        rows = self.db.fetchall(
            "SELECT TRIM(code) AS code, COALESCE(SUM(qty),0) AS qty, COALESCE(SUM(weight),0) AS weight "
            "FROM itemsstk GROUP BY TRIM(code)")
        for r in rows:
            out[str(r["code"])] = {"qty": money(r["qty"]), "weight": money(r["weight"])}
        return out

    def _movement(self, detail: str, master: str, date1: str, date2: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        if not self.db.table_exists(detail) or not self.db.table_exists(master):
            return out
        rows = self.db.fetchall(
            f"SELECT TRIM(d.code) AS code, COALESCE(SUM(d.qty),0) AS qty, COALESCE(SUM(d.weight),0) AS weight "
            f"FROM {detail} d JOIN {master} m ON d.slno = m.slno "
            f"WHERE m.tdate BETWEEN :d1 AND :d2 AND m.control <= :g GROUP BY TRIM(d.code)",
            {"d1": date1, "d2": date2, "g": self.rlevel})
        for r in rows:
            out[str(r["code"])] = {"qty": money(r["qty"]), "weight": money(r["weight"])}
        return out

    def summary(self, date1: str, date2: str, itype: str = "", grpcode: str = "") -> list[dict]:
        if not self.db.table_exists("items"):
            return []
        sql = "SELECT TRIM(code) AS code, name, itype, grpcode FROM items WHERE 1=1"
        params: dict = {}
        if itype:
            sql += " AND itype = :it"; params["it"] = itype
        if grpcode:
            sql += " AND grpcode = :gp"; params["gp"] = grpcode
        sql += " ORDER BY code"
        items = self.db.fetchall(sql, params)

        opening = self._opening()
        moves = {name: self._movement(name, mast, date1, date2) for name, mast, _s in _MOVES}

        result = []
        for it in items:
            code = str(it["code"])
            op = opening.get(code, {"qty": Decimal("0"), "weight": Decimal("0")})
            close_q = op["qty"]
            close_w = op["weight"]
            cells = {"op_qty": op["qty"], "op_weight": op["weight"]}
            for name, _mast, sign in _MOVES:
                mv = moves[name].get(code, {"qty": Decimal("0"), "weight": Decimal("0")})
                cells[f"{name}_qty"] = mv["qty"]
                cells[f"{name}_weight"] = mv["weight"]
                close_q = money(close_q + sign * mv["qty"])
                close_w = money(close_w + sign * mv["weight"])
            # skip all-zero items to match a register's non-empty rows
            if all(v == 0 for v in (op["qty"], op["weight"], close_q, close_w)) and \
               all(cells[f"{n}_weight"] == 0 for n, _m, _s in _MOVES):
                continue
            result.append({"code": code, "name": str(it.get("name") or ""),
                           "itype": str(it.get("itype") or ""),
                           "op_qty": op["qty"], "op_weight": op["weight"],
                           "close_qty": close_q, "close_weight": close_w, **cells})
        return result
