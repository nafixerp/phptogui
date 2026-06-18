"""TDS Report — port of TdsReportController::data.

Goldsmith making-charge TDS: rows from ``smithm`` where ``tdsamt > 0`` in the
period, with the smith name/ctype joined from ``clients`` (and ``clientsgs``
for the grouped ctype). Optional party-code and ctype (J/G) filters.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money

_ZERO = Decimal("0")


class TdsReportService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = max(1, int(rlevel or 1))

    def report(self, date1: str, date2: str, code: str = "", ctype: str = "") -> dict:
        if not self.db.table_exists("smithm"):
            return {"rows": [], "totals": {"tmcharge": _ZERO, "tdsamt": _ZERO}}
        has_clients = self.db.table_exists("clients")
        has_gs = self.db.table_exists("clientsgs")
        name = "TRIM(COALESCE(c.name,''))" if has_clients else "''"
        if has_clients and has_gs:
            ctype_sel = "TRIM(COALESCE(gs.ctype, c.ctype, ''))"
        elif has_clients:
            ctype_sel = "TRIM(COALESCE(c.ctype, ''))"
        else:
            ctype_sel = "''"
        join = ""
        if has_clients:
            join = "LEFT JOIN clients c ON TRIM(c.code) = TRIM(sm.smithcode) "
            if has_gs:
                join += "LEFT JOIN clientsgs gs ON gs.code = c.code "
        where = ["sm.tdsamt > 0", "sm.tdate >= :f", "sm.tdate <= :t", "sm.control <= :g"]
        params: dict = {"f": date1, "t": date2, "g": self.rlevel}
        if code.strip():
            where.append("TRIM(sm.smithcode) = :cd"); params["cd"] = code.strip()
        if ctype.strip().upper() in ("J", "G") and has_clients:
            col = "gs.ctype" if has_gs else "c.ctype"
            where.append(f"{col} = :ct"); params["ct"] = ctype.strip().upper()
        rows = self.db.fetchall(
            f"SELECT sm.tdate, TRIM(sm.docno) AS docno, TRIM(sm.smithcode) AS smithcode, "
            f"COALESCE(sm.tmcharge,0) AS tmcharge, COALESCE(sm.tdsperc,0) AS tdsperc, "
            f"COALESCE(sm.tdsamt,0) AS tdsamt, {name} AS name, {ctype_sel} AS ctype "
            f"FROM smithm sm {join}WHERE {' AND '.join(where)} "
            "ORDER BY sm.tdate, sm.docno LIMIT 5000", params)
        out = []; tot_tmc = _ZERO; tot_tds = _ZERO
        for r in rows:
            tmc = money(r.get("tmcharge")); tds = money(r.get("tdsamt"))
            out.append({
                "tdate": str(r.get("tdate") or ""), "docno": str(r.get("docno") or ""),
                "smithcode": str(r.get("smithcode") or ""), "name": str(r.get("name") or ""),
                "ctype": str(r.get("ctype") or ""), "tmcharge": tmc,
                "tdsperc": money(r.get("tdsperc")), "tdsamt": tds,
            })
            tot_tmc += tmc; tot_tds += tds
        return {"rows": out, "totals": {"tmcharge": tot_tmc, "tdsamt": tot_tds}}
