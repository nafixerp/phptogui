"""Party Outstanding — receivable / payable balances per party.

Read core of CustomerReports / SupplierReports duedate reports:

    netbal(accode) = accountm.opbal|opbalb  +  Σ daybook.amount
                     (control <= gilevel, tdate <= as-of)

joined to ``clients`` for name/mobile. Suppliers are ``accountm.actype2 = 'S'``;
customers are the rest of the party accounts. Zero balances are dropped. With
the signed-amount convention a positive net = payable (TG), negative =
receivable (TR).
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money

_ZERO = Decimal("0")


class PartyOutstandingService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = max(1, int(gilevel or 1))

    def _opcol(self) -> str:
        if self.gilevel == 1:
            return "opbal"
        return "opbalb" if self.db.column_exists("accountm", "opbalb") else "opbal"

    def outstanding(self, party_type: str = "Supplier", as_of: str | None = None,
                    name: str = "") -> dict:
        if not self.db.table_exists("accountm"):
            return {"rows": [], "totals": {"tr": _ZERO, "tg": _ZERO, "count": 0}}
        opcol = self._opcol()
        has_clients = self.db.table_exists("clients")
        cname = "TRIM(COALESCE(c.name,''))" if has_clients else "''"
        mobile = "TRIM(COALESCE(c.mobile,''))" if has_clients else "''"
        join = "LEFT JOIN clients c ON TRIM(c.code) = TRIM(a.accode) " if has_clients else ""
        mv = "0"
        params: dict = {"g": self.gilevel}
        if self.db.table_exists("daybook"):
            dcond = ""
            if as_of:
                dcond = "AND d.tdate <= :asof"; params["asof"] = as_of
            mv = ("COALESCE((SELECT SUM(d.amount) FROM daybook d "
                  f"WHERE TRIM(d.accode) = TRIM(a.accode) AND d.control <= :g {dcond}),0)")
        where = ["a.control <= :g"] if self.db.column_exists("accountm", "control") else ["1=1"]
        if party_type == "Supplier" and self.db.column_exists("accountm", "actype2"):
            where.append("TRIM(COALESCE(a.actype2,'')) = 'S'")
        elif party_type == "Customer" and self.db.column_exists("accountm", "actype2"):
            where.append("TRIM(COALESCE(a.actype2,'')) <> 'S'")
        if name.strip() and has_clients:
            where.append("UPPER(c.name) LIKE :nm"); params["nm"] = f"%{name.strip().upper()}%"
        rows = self.db.fetchall(
            f"SELECT TRIM(a.accode) AS accode, {cname} AS cname, {mobile} AS mobile, "
            f"COALESCE(a.{opcol},0) AS opbal, {mv} AS movement, "
            f"(COALESCE(a.{opcol},0) + {mv}) AS netbal "
            f"FROM accountm a {join}WHERE {' AND '.join(where)} "
            "ORDER BY cname LIMIT 10000", params)
        out = []; tr = _ZERO; tg = _ZERO
        for r in rows:
            netbal = money(r.get("netbal"))
            if abs(netbal) < Decimal("0.01"):
                continue
            status = "TG" if netbal > 0 else "TR"
            absbal = money(abs(netbal))
            out.append({"accode": str(r.get("accode") or ""), "cname": str(r.get("cname") or ""),
                        "mobile": str(r.get("mobile") or ""), "netbal": netbal, "bal_abs": absbal,
                        "status": status})
            if status == "TR":
                tr += absbal
            else:
                tg += absbal
        return {"rows": out, "totals": {"tr": tr, "tg": tg, "count": len(out)}}
