"""Smith Book (read-only) — goldsmith transaction ledger from smithm/smithd.

Lists a goldsmith's transactions in a date range (control <= rlevel) with the
issued/received weight totals from smithd, and the net weight balance.
smithd.givrec marks give ('G'/issue) vs receive ('R').
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import weight


class SmithBookService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = int(rlevel or 1)

    def transactions(self, smithcode: str, date1: str, date2: str) -> dict:
        smithcode = str(smithcode or "").strip().upper()
        if not self.db.table_exists("smithm"):
            return {"rows": [], "issued": Decimal("0"), "received": Decimal("0"), "balance": Decimal("0")}

        rows = self.db.fetchall(
            "SELECT m.slno, m.docno, m.tdate, TRIM(m.smithcode) AS smithcode, "
            "COALESCE(m.netamt,0) AS netamt, COALESCE(m.rate,0) AS rate, "
            "COALESCE(m.tmcharge,0) AS tmcharge "
            "FROM smithm m WHERE UPPER(TRIM(m.smithcode)) = :c "
            "AND m.tdate BETWEEN :d1 AND :d2 AND m.control <= :g ORDER BY m.tdate, m.slno",
            {"c": smithcode, "d1": date1, "d2": date2, "g": self.rlevel},
        )

        issued = Decimal("0")
        received = Decimal("0")
        has_detail = self.db.table_exists("smithd")
        for r in rows:
            iw = rw = Decimal("0")
            if has_detail:
                det = self.db.fetchall(
                    "SELECT COALESCE(givrec,'') AS givrec, COALESCE(SUM(weight),0) AS w "
                    "FROM smithd WHERE slno = :s GROUP BY givrec", {"s": r["slno"]})
                for d in det:
                    gv = str(d["givrec"] or "").strip().upper()
                    w = weight(d["w"])
                    if gv in ("R", "RECEIVE", "RCV"):
                        rw += w
                    else:
                        iw += w
            r["issued_wgt"] = iw
            r["received_wgt"] = rw
            issued += iw
            received += rw
        return {"rows": rows, "issued": weight(issued), "received": weight(received),
                "balance": weight(issued - received)}
