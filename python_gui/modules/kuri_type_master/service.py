"""Kuri (chit) Type Master — port of KuriTypeMasterController.

`kuritype` defines each scheme: instalment count/amount, total, bonus,
collection type, prefix/last-no, limits and commission. ``save`` is a full
replace (delete-all then insert), column-filtered against the live schema. A
type referenced by an enrolled member (``clients_kuridet``) can't be dropped —
callers should guard with ``in_use``.
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import money, to_decimal

_FIELDS = ["code", "name", "instnos", "instamt", "totamt", "bonus", "colntype",
           "comnperc", "prefix", "lastno", "collnlimit", "collnmin", "comnrate"]


class KuriTypeMasterService:
    def __init__(self, database: Database):
        self.db = database

    def load(self) -> list[dict]:
        if not self.db.table_exists("kuritype"):
            return []
        return self.db.fetchall("SELECT * FROM kuritype ORDER BY code")

    def in_use(self, code: str) -> bool:
        if not self.db.table_exists("clients_kuridet"):
            return False
        return bool(self.db.fetchone(
            "SELECT 1 FROM clients_kuridet WHERE TRIM(kuritype) = :c LIMIT 1",
            {"c": str(code).strip().upper()}))

    def save(self, rows: list[dict]) -> str:
        if not self.db.table_exists("kuritype"):
            raise RuntimeError("kuritype table not found")
        cols = set(self.db.columns("kuritype"))
        n = 0
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM kuritype")
            for r in rows:
                code = str(r.get("code") or "").strip().upper()
                name = str(r.get("name") or "").strip()
                if not code or not name:
                    continue
                data = {
                    "code": code, "name": name,
                    "instnos": int(r.get("instnos") or 0),
                    "instamt": money(r.get("instamt")), "totamt": money(r.get("totamt")),
                    "bonus": money(r.get("bonus")),
                    "colntype": str(r.get("colntype") or "M").strip().upper(),
                    "comnperc": to_decimal(r.get("comnperc")),
                    "prefix": str(r.get("prefix") or "").strip().upper(),
                    "lastno": int(r.get("lastno") or 0),
                    "collnlimit": money(r.get("collnlimit")), "collnmin": money(r.get("collnmin")),
                    "comnrate": to_decimal(r.get("comnrate")),
                }
                use = {k: v for k, v in data.items() if k in cols}
                names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
                tx.execute(f"INSERT INTO kuritype ({names}) VALUES ({binds})", use)
                n += 1
        return f"Saved {n} type(s)"
