"""Extra Amount Report — port of ExtraAmtReportController::data.

Per goldsmith voucher (``smithm``) in a date range: the making charge, plus the
"extra" charge heads — acid charge and discount (both column-guarded, default 0)
— and TDS. Smith name joined from ``clients``. Optional party-code filter.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money

_ZERO = Decimal("0")


class ExtraAmtReportService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = max(1, int(rlevel or 1))

    def _col(self, t: str, c: str) -> bool:
        return self.db.table_exists(t) and self.db.column_exists(t, c)

    def report(self, date1: str, date2: str, code: str = "") -> dict:
        if not self.db.table_exists("smithm"):
            return {"rows": [], "totals": {"acidcharge": _ZERO, "discount": _ZERO,
                                           "tmcharge": _ZERO, "tdsamt": _ZERO}}
        acid = "COALESCE(sm.acidcharge,0)" if self._col("smithm", "acidcharge") else "0"
        disc = "COALESCE(sm.discount,0)" if self._col("smithm", "discount") else "0"
        name = "TRIM(COALESCE(c.name,''))" if self.db.table_exists("clients") else "''"
        join = "LEFT JOIN clients c ON TRIM(c.code) = TRIM(sm.smithcode) " if self.db.table_exists("clients") else ""
        where = ["sm.tdate >= :f", "sm.tdate <= :t", "sm.control <= :g"]
        params: dict = {"f": date1, "t": date2, "g": self.rlevel}
        if code.strip():
            where.append("TRIM(sm.smithcode) = :cd"); params["cd"] = code.strip()
        rows = self.db.fetchall(
            f"SELECT sm.tdate, TRIM(sm.docno) AS docno, TRIM(sm.smithcode) AS smithcode, "
            f"COALESCE(sm.tmcharge,0) AS tmcharge, COALESCE(sm.tdsamt,0) AS tdsamt, "
            f"{acid} AS acidcharge, {disc} AS discount, {name} AS name "
            f"FROM smithm sm {join}WHERE {' AND '.join(where)} "
            "ORDER BY sm.tdate, sm.docno LIMIT 5000", params)
        out = []; tot = {"acidcharge": _ZERO, "discount": _ZERO, "tmcharge": _ZERO, "tdsamt": _ZERO}
        for r in rows:
            acid_v = money(r.get("acidcharge")); disc_v = money(r.get("discount"))
            tmc = money(r.get("tmcharge")); tds = money(r.get("tdsamt"))
            # only show vouchers that carry an extra amount
            if acid_v == 0 and disc_v == 0:
                continue
            out.append({"tdate": str(r.get("tdate") or ""), "docno": str(r.get("docno") or ""),
                        "smithcode": str(r.get("smithcode") or ""), "name": str(r.get("name") or ""),
                        "tmcharge": tmc, "acidcharge": acid_v, "discount": disc_v, "tdsamt": tds})
            tot["acidcharge"] += acid_v; tot["discount"] += disc_v
            tot["tmcharge"] += tmc; tot["tdsamt"] += tds
        return {"rows": out, "totals": tot}
