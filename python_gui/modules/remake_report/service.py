"""Remake Report — port of RemakeReportController (remake return details).

Repair-return bills (``repairm.givrec = 'G'``) in a date range with their
``repaird`` item lines. Net charge = amount + tax - discount; balance = net -
received. Column-guarded amount heads and optional customer filter.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money, weight as wq

_ZERO = Decimal("0")


class RemakeReportService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = max(1, int(rlevel or 1))

    def report(self, date1: str, date2: str, custcode: str = "") -> list[dict]:
        if not self.db.table_exists("repairm"):
            return []
        amt_cols = [c for c in ("amount", "discount", "rcvd", "taxamt")
                    if self.db.column_exists("repairm", c)]
        sel = ", ".join(f"COALESCE(m.{c},0) AS {c}" for c in amt_cols)
        where = ["m.givrec = 'G'", "m.tdate BETWEEN :f AND :t"]
        params: dict = {"f": date1, "t": date2}
        if custcode.strip():
            where.append("m.custcode = :cc"); params["cc"] = custcode.strip()
        masters = self.db.fetchall(
            f"SELECT m.slno, m.billno, m.tdate, m.custcode, m.custname, m.rbillno, m.sman"
            f"{(', ' + sel) if sel else ''} FROM repairm m WHERE {' AND '.join(where)} "
            "ORDER BY m.tdate, m.slno LIMIT 5000", params)
        if not masters:
            return []
        details: dict = {}
        if self.db.table_exists("repaird"):
            slnos = [m["slno"] for m in masters]
            ph = ", ".join(f":s{i}" for i in range(len(slnos)))
            drows = self.db.fetchall(
                f"SELECT slno, sno, code, name, qty, weight, stonewgt, netwgt FROM repaird "
                f"WHERE slno IN ({ph}) ORDER BY slno, sno",
                {f"s{i}": v for i, v in enumerate(slnos)})
            for d in drows:
                details.setdefault(d["slno"], []).append(d)
        out = []
        for m in masters:
            items = [{"sno": int(d.get("sno") or 0), "code": str(d.get("code") or "").strip(),
                      "name": str(d.get("name") or "").strip(), "qty": int(d.get("qty") or 0),
                      "weight": wq(d.get("weight")), "stonewgt": wq(d.get("stonewgt")),
                      "netwgt": wq(d.get("netwgt"))} for d in details.get(m["slno"], [])]
            amount = money(m.get("amount")); discount = money(m.get("discount"))
            taxamt = money(m.get("taxamt")); rcvd = money(m.get("rcvd"))
            netamt = money(amount + taxamt - discount)
            out.append({
                "slno": m["slno"], "billno": str(m.get("billno") or "").strip(),
                "tdate": str(m.get("tdate") or ""), "custcode": str(m.get("custcode") or "").strip(),
                "custname": str(m.get("custname") or "").strip(), "rbillno": str(m.get("rbillno") or "").strip(),
                "sman": str(m.get("sman") or "").strip(), "amount": amount, "discount": discount,
                "taxamt": taxamt, "netamt": netamt, "rcvd": rcvd, "balance": money(netamt - rcvd),
                "items": items, "tot_wgt": sum((it["weight"] for it in items), _ZERO),
                "tot_net": sum((it["netwgt"] for it in items), _ZERO), "item_count": len(items)})
        return out
