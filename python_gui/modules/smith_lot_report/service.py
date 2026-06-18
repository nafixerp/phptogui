"""Smith Lot Report — port of SmithLotReportController::data.

Per smith (client) × lot number, the issued / received net weight & qty within
the period (``smithd.givrec`` G = issued, R = received), and the pending balance
(issued - received). Smith codes optional filter.
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import weight as wq


class SmithLotReportService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = max(1, int(rlevel or 1))

    def report(self, date1: str, date2: str, smith: str = "") -> list[dict]:
        if not (self.db.table_exists("clients") and self.db.table_exists("smithm")
                and self.db.table_exists("smithd")):
            return []
        sub = ("(SELECT COALESCE(SUM(sd.{col}),0) FROM smithd sd JOIN smithm sm2 ON sm2.slno=sd.slno "
               "WHERE sm2.smithcode=c.code AND sd.givrec=:{gr} AND sm2.lotno=sm.lotno "
               "AND sm2.control<=:g AND sm2.tdate>=:f AND sm2.tdate<=:t)")
        params = {"g": self.rlevel, "f": date1, "t": date2}
        where = ["sm.lotno <> ''", "sm.lotno IS NOT NULL"]
        if smith.strip():
            where.append("c.code = :sc"); params["sc"] = smith.strip()
        rows = self.db.fetchall(
            "SELECT TRIM(c.code) AS code, TRIM(c.name) AS name, TRIM(sm.lotno) AS lotno, "
            f"COALESCE({sub.format(col='netwgt', gr='gG')},0) AS issuewgt, "
            f"COALESCE({sub.format(col='netwgt', gr='gR')},0) AS rcvdwgt, "
            f"COALESCE({sub.format(col='qty', gr='gG2')},0) AS issueqty, "
            f"COALESCE({sub.format(col='qty', gr='gR2')},0) AS rcvdqty "
            "FROM clients c JOIN smithm sm ON sm.smithcode = c.code "
            f"WHERE {' AND '.join(where)} "
            "GROUP BY c.code, c.name, sm.lotno ORDER BY c.name",
            {**params, "gG": "G", "gR": "R", "gG2": "G", "gR2": "R"})
        out = []
        for r in rows:
            iw = wq(r.get("issuewgt")); rw = wq(r.get("rcvdwgt"))
            iq = int(r.get("issueqty") or 0); rq = int(r.get("rcvdqty") or 0)
            out.append({
                "code": str(r.get("code") or "").strip(), "name": str(r.get("name") or "").strip(),
                "lotno": str(r.get("lotno") or "").strip(),
                "issuewgt": iw, "rcvdwgt": rw, "pendwgt": wq(iw - rw),
                "issueqty": iq, "rcvdqty": rq, "pendqty": iq - rq,
            })
        return out
