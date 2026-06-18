"""Misc reports — Non-Transactional Days and Gold Rate History.

- ``non_transactional_days``: every date in the range that has **no** activity
  in ``daybook`` or ``smithm`` (the "holidays"). Port of
  NonTransactionalDaysReportController.
- ``gold_rate_history``: the ``ratehistory`` ledger over a range (gold 22k/18k,
  silver, platinum). Port of GoldRateStoryController's rate source.
"""

from __future__ import annotations

from datetime import date, timedelta

from ...core.db import Database
from ...core.decimals import money


def _parse(d) -> date | None:
    try:
        return date.fromisoformat(str(d or "").strip()[:10])
    except ValueError:
        return None


class MiscReportsService:
    def __init__(self, database: Database):
        self.db = database

    def non_transactional_days(self, date1: str, date2: str) -> list[dict]:
        start = _parse(date1); end = _parse(date2)
        if start is None or end is None or end < start:
            return []
        active: set[str] = set()
        for table in ("daybook", "smithm"):
            if self.db.table_exists(table):
                rows = self.db.fetchall(
                    f"SELECT tdate, COUNT(*) AS n FROM {table} "
                    "WHERE tdate BETWEEN :f AND :t GROUP BY tdate",
                    {"f": date1, "t": date2})
                for r in rows:
                    if int(r.get("n") or 0) > 0:
                        active.add(str(r.get("tdate"))[:10])
        out = []; sno = 1; cur = start
        while cur <= end:
            key = cur.isoformat()
            if key not in active:
                out.append({"sno": sno, "tdate": key}); sno += 1
            cur += timedelta(days=1)
        return out

    def gold_rate_history(self, date1: str, date2: str) -> list[dict]:
        if not self.db.table_exists("ratehistory"):
            return []
        cols = set(self.db.columns("ratehistory"))
        wanted = [c for c in ("grate", "g18rate", "srate", "prate") if c in cols]
        sel = ", ".join(f"COALESCE({c},0) AS {c}" for c in wanted)
        rows = self.db.fetchall(
            f"SELECT tdate{(', ' + sel) if sel else ''} FROM ratehistory "
            "WHERE tdate BETWEEN :f AND :t ORDER BY tdate DESC LIMIT 2000",
            {"f": date1, "t": date2})
        return [{"tdate": str(r.get("tdate") or ""), **{c: money(r.get(c)) for c in wanted}} for r in rows]
