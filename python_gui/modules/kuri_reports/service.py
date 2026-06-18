"""Kuri (chit) reports — Finish/Maturity list and Interest-Post list.

- ``finish_list``: unfinished members (``clients.grp = 'KC'`` joined to
  ``clients_kuridet.finished = 'N'``) with total collection (kuricolln + opening
  balance), balance = totamt - collected, and estimated maturity weight
  (totamt / gold-rate). Port of KuriFinishController.
- ``interest_list``: per member, simple interest accrued on each kuricolln
  entry: ``amount * intrate/100 * days/365`` (days from collection date to the
  cut-off). Port of KuriIntPostController. Computed in Python to stay
  DB-agnostic (no MySQL DATEDIFF).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, quantize, to_decimal

_ZERO = Decimal("0")
_WT = Decimal("0.001")


def _parse(d) -> date | None:
    s = str(d or "").strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


class KuriReportsService:
    def __init__(self, database: Database, control: int = 1):
        self.db = database
        self.control = max(1, int(control or 1))

    def _has(self, t: str) -> bool:
        return self.db.table_exists(t)

    def _collected(self, code: str, tdate: str) -> Decimal:
        if not self._has("kuricolln"):
            return _ZERO
        v = self.db.scalar(
            "SELECT COALESCE(SUM(amount),0) FROM kuricolln "
            "WHERE code = :c AND tdate <= :t AND control <= :g",
            {"c": code, "t": tdate, "g": self.control})
        return money(v)

    def finish_list(self, tdate: str, grate, stype: str = "") -> list[dict]:
        if not (self._has("clients") and self._has("clients_kuridet")):
            return []
        grate = to_decimal(grate) or _ZERO
        where = ["c.grp = 'KC'", "kd.finished = 'N'"]
        params: dict = {}
        if stype.strip():
            where.append("kd.kuritype = :st"); params["st"] = stype.strip()
        rows = self.db.fetchall(
            "SELECT TRIM(kd.code) AS code, TRIM(c.name) AS name, "
            "COALESCE(kd.totamt,0) AS totamt, COALESCE(kd.bonus,0) AS bonus, "
            "COALESCE(kd.collnopbal,0) AS opbal, COALESCE(kd.kuritype,'') AS kuritype "
            "FROM clients_kuridet kd JOIN clients c ON c.code = kd.code "
            f"WHERE {' AND '.join(where)} ORDER BY c.name LIMIT 500", params)
        out = []
        for r in rows:
            code = str(r.get("code") or "").strip()
            if not code:
                continue
            totamt = money(r.get("totamt"))
            collected = money(self._collected(code, tdate) + money(r.get("opbal")))
            estwgt = quantize(totamt / grate, _WT) if grate > 0 else _ZERO
            out.append({
                "code": code, "name": str(r.get("name") or "").strip(),
                "totamt": totamt, "tcolln": collected, "balance": money(totamt - collected),
                "bonus": money(r.get("bonus")), "estwgt": estwgt,
            })
        return out

    def interest_list(self, tdate: str, with_zero: bool = False) -> list[dict]:
        if not self._has("clients"):
            return []
        rows = self.db.fetchall(
            "SELECT TRIM(c.code) AS code, TRIM(c.name) AS name, "
            "COALESCE((SELECT intrate FROM clients_kuridet ckd WHERE ckd.code = c.code LIMIT 1),0) AS intrate "
            "FROM clients c WHERE c.grp = 'KC' ORDER BY c.name LIMIT 1000")
        cutoff = _parse(tdate) or date.today()
        out = []
        for r in rows:
            code = str(r.get("code") or "").strip()
            if not code:
                continue
            intrate = to_decimal(r.get("intrate")) or _ZERO
            tcolln = self._collected(code, tdate)
            intamt = _ZERO
            if intrate > 0 and not with_zero and self._has("kuricolln"):
                intamt = self._interest(code, tdate, intrate, cutoff)
            elif with_zero:
                intamt = _ZERO
            out.append({
                "code": code, "name": str(r.get("name") or "").strip(),
                "tcolln": money(tcolln), "intrate": quantize(intrate, _WT), "intamt": money(intamt),
            })
        return out

    def _interest(self, code: str, tdate: str, intrate: Decimal, cutoff: date) -> Decimal:
        rows = self.db.fetchall(
            "SELECT amount, tdate FROM kuricolln "
            "WHERE code = :c AND tdate <= :t AND control <= :g",
            {"c": code, "t": tdate, "g": self.control})
        total = _ZERO
        for r in rows:
            amt = money(r.get("amount"))
            d = _parse(r.get("tdate"))
            if d is None:
                continue
            days = (cutoff - d).days
            if days <= 0:
                continue
            total += amt * intrate / 100 * Decimal(days) / 365
        return money(total)
