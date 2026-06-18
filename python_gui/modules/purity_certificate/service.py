"""Purity Certificate — port of PurityCertificateController.

Previews the next certificate number (``generali.PURITYCERTNO`` + 1), searches
items for the certificate body, and increments the counter when a certificate
is issued.
"""

from __future__ import annotations

from ...core.db import Database

COUNTER_KEY = "PURITYCERTNO"


class PurityCertificateService:
    def __init__(self, database: Database):
        self.db = database

    def next_cert_no(self) -> int:
        cur = 0
        if self.db.table_exists("generali"):
            cur = int(self.db.scalar(
                "SELECT cvalue FROM generali WHERE TRIM(code) = :c", {"c": COUNTER_KEY}) or 0)
        return cur + 1

    def search_items(self, search: str) -> list[dict]:
        if not self.db.table_exists("items") or not search.strip():
            return []
        like = f"%{search.strip().upper()}%"
        return self.db.fetchall(
            "SELECT TRIM(code) AS code, TRIM(name) AS name FROM items "
            "WHERE UPPER(code) LIKE :q OR UPPER(name) LIKE :q ORDER BY code LIMIT 50",
            {"q": like})

    def increment(self) -> int:
        if not self.db.table_exists("generali"):
            raise RuntimeError("generali not found")
        with self.db.transaction() as tx:
            exists = tx.fetchall(
                "SELECT 1 FROM generali WHERE TRIM(code) = :c LIMIT 1", {"c": COUNTER_KEY})
            if not exists:
                tx.execute("INSERT INTO generali (code, cvalue) VALUES (:c, 0)", {"c": COUNTER_KEY})
            tx.execute("UPDATE generali SET cvalue = cvalue + 1 WHERE TRIM(code) = :c", {"c": COUNTER_KEY})
        return self.next_cert_no()
