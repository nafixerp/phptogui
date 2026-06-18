"""Account reports — Chart of Accounts, Cash Balance, Group Summary.

All three rest on the same balance rule used by the ledger:

    balance(accode) = accountm.opbal|opbalb  +  Σ daybook.amount
                      (control <= gilevel, tdate <= as-of)

with the signed-amount convention (negative = debit, positive = credit). Group
name comes from `accountg` when present. Ports of ChartOfAccountsController,
CashBalanceController and the group rollup of AcSummary.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money

_ZERO = Decimal("0")
_ACTYPE = {"Assets Only": "A", "Liabilities Only": "L", "Expenses Only": "E", "Incomes Only": "R"}


class AccountReportsService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = max(1, int(gilevel or 1))

    def _opcol(self) -> str:
        if self.gilevel == 1:
            return "opbal"
        return "opbalb" if self.db.column_exists("accountm", "opbalb") else "opbal"

    def _col(self, t: str, c: str) -> bool:
        return self.db.table_exists(t) and self.db.column_exists(t, c)

    def chart_of_accounts(self, as_of: str, type_: str = "All", grcode: str = "",
                          with_balance: bool = False) -> list[dict]:
        if not self.db.table_exists("accountm"):
            return []
        opcol = self._opcol()
        has_g = self.db.table_exists("accountg")
        gname = "TRIM(COALESCE(g.name,''))" if has_g else "''"
        join = "LEFT JOIN accountg g ON g.grcode = a.grcode " if has_g else ""
        mv = "0"
        if self.db.table_exists("daybook"):
            mv = ("COALESCE((SELECT SUM(d.amount) FROM daybook d "
                  "WHERE TRIM(d.accode) = TRIM(a.accode) AND d.control <= :g AND d.tdate <= :asof),0)")
        where = ["1=1"]
        params: dict = {"g": self.gilevel, "asof": as_of}
        if type_ in _ACTYPE and self._col("accountm", "actype1"):
            where.append("TRIM(COALESCE(a.actype1,'')) = :ty"); params["ty"] = _ACTYPE[type_]
        if grcode.strip() and self._col("accountm", "grcode"):
            where.append("TRIM(COALESCE(a.grcode,'')) = :gc"); params["gc"] = grcode.strip()
        rows = self.db.fetchall(
            f"SELECT TRIM(a.accode) AS accode, TRIM(COALESCE(a.name,'')) AS acname, "
            f"TRIM(COALESCE(a.grcode,'')) AS grcode, {gname} AS group_name, "
            f"COALESCE(a.{opcol},0) AS opening_balance, {mv} AS movement, "
            f"(COALESCE(a.{opcol},0) + {mv}) AS balance "
            f"FROM accountm a {join}WHERE {' AND '.join(where)} "
            "ORDER BY group_name, a.name LIMIT 10000", params)
        out = []
        for r in rows:
            bal = money(r.get("balance"))
            if with_balance and bal == 0:
                continue
            out.append({
                "accode": str(r.get("accode") or ""), "acname": str(r.get("acname") or ""),
                "grcode": str(r.get("grcode") or ""), "group_name": str(r.get("group_name") or ""),
                "opening": money(r.get("opening_balance")), "movement": money(r.get("movement")),
                "balance": bal,
                "debit": money(-bal) if bal < 0 else _ZERO,
                "credit": bal if bal > 0 else _ZERO,
            })
        return out

    def cash_balance(self, as_of: str | None = None, accode: str = "CASH") -> Decimal:
        if not self.db.table_exists("accountm"):
            return _ZERO
        opcol = self._opcol()
        acc = self.db.fetchone(
            f"SELECT COALESCE({opcol},0) AS ob FROM accountm WHERE TRIM(accode) = :c LIMIT 1",
            {"c": accode})
        bal = money(acc.get("ob")) if acc else _ZERO
        if self.db.table_exists("daybook"):
            params = {"c": accode, "g": self.gilevel}
            dcond = ""
            if as_of:
                dcond = "AND tdate <= :asof"; params["asof"] = as_of
            mv = self.db.scalar(
                f"SELECT COALESCE(SUM(amount),0) FROM daybook "
                f"WHERE TRIM(accode) = :c AND control <= :g {dcond}", params)
            bal = money(bal + money(mv))
        return bal

    def group_summary(self, as_of: str, type_: str = "All") -> list[dict]:
        rows = self.chart_of_accounts(as_of, type_)
        agg: dict[str, dict] = {}
        for r in rows:
            key = r["group_name"] or r["grcode"] or "(ungrouped)"
            g = agg.setdefault(key, {"group": key, "debit": _ZERO, "credit": _ZERO, "count": 0})
            g["debit"] += r["debit"]; g["credit"] += r["credit"]; g["count"] += 1
        return [{"group": k, "debit": money(v["debit"]), "credit": money(v["credit"]),
                 "balance": money(v["credit"] - v["debit"]), "count": v["count"]}
                for k, v in sorted(agg.items())]
