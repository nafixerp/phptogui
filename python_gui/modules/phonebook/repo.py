"""Phone Book repository — read-only directory over `clients`.

Source: app/Http/Controllers/PhoneBookController.php (loadContacts / quickLookup).
No writes. Optionally left-joins `clients_advanced` for birthday/engagement/
marriage dates when those columns exist.
"""

from __future__ import annotations

from ...core.db import Database

_ADVANCED_DATE_COLS = ["dtbirthday", "dtengagement", "dtmarriage"]

# Base TRIM(COALESCE(...)) selects from loadContacts().
_BASE_SELECT = [
    "c.code AS code", "c.name AS name",
    "TRIM(COALESCE(c.addr1, '')) AS addr1", "TRIM(COALESCE(c.addr2, '')) AS addr2",
    "TRIM(COALESCE(c.addr3, '')) AS addr3", "TRIM(COALESCE(c.city, '')) AS city",
    "TRIM(COALESCE(c.telephone, '')) AS telephone", "TRIM(COALESCE(c.mobile, '')) AS mobile",
    "TRIM(COALESCE(c.email, '')) AS email", "TRIM(COALESCE(c.ctype, '')) AS ctype",
    "TRIM(COALESCE(c.grp, '')) AS grp", "TRIM(COALESCE(c.route, '')) AS route",
    "TRIM(COALESCE(c.carea, '')) AS carea",
]


class PhoneBookRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_clients(self) -> bool:
        return self.db.table_exists("clients")

    def _columns(self, table: str) -> set[str]:
        return set(self.db.columns(table))

    def load_contacts(self, ctype: str, search: str, contact_status: str) -> list[dict]:
        if not self.has_clients():
            return []

        client_cols = self._columns("clients")
        has_advanced = self.db.table_exists("clients_advanced")
        advanced_cols = self._columns("clients_advanced") if has_advanced else set()

        selects = list(_BASE_SELECT)
        join = ""
        if has_advanced:
            join = " LEFT JOIN clients_advanced AS a ON a.code = c.code"
            for col in _ADVANCED_DATE_COLS:
                if col in advanced_cols:
                    selects.append(f"a.{col} AS {col}")

        where = ["1=1"]
        params: dict = {}
        if "removed" in client_cols:
            where.append("(c.removed IS NULL OR c.removed <> 1)")
        if ctype != "ALL":
            where.append("c.ctype = :ctype")
            params["ctype"] = ctype

        search = search.strip()
        if search:
            params["s"] = f"%{search}%"
            where.append(
                "(c.code LIKE :s OR c.name LIKE :s OR c.mobile LIKE :s "
                "OR c.telephone LIKE :s OR c.email LIKE :s OR c.city LIKE :s)"
            )

        status = contact_status.strip().lower()
        if status == "mobile-only":
            where.append("TRIM(COALESCE(c.mobile, '')) <> ''")
        elif status == "missing-mobile":
            where.append("TRIM(COALESCE(c.mobile, '')) = ''")
        elif status == "any-contact":
            where.append("(TRIM(COALESCE(c.mobile, '')) <> '' OR TRIM(COALESCE(c.telephone, '')) <> '' "
                         "OR TRIM(COALESCE(c.email, '')) <> '')")

        sql = (f"SELECT {', '.join(selects)} FROM clients AS c{join} "
               f"WHERE {' AND '.join(where)} ORDER BY c.name LIMIT 800")
        return self.db.fetchall(sql, params)

    def quick_lookup(self, needle: str, digits: str) -> list[dict]:
        if not self.has_clients() or needle.strip() == "":
            return []
        params = {"like": f"%{needle}%"}
        digit_clause = ""
        if digits:
            params["dlike"] = f"%{digits}%"
            digit_clause = (
                " OR REGEXP_REPLACE(COALESCE(c.mobile, ''), '[^0-9]', '') LIKE :dlike"
                " OR REGEXP_REPLACE(COALESCE(c.telephone, ''), '[^0-9]', '') LIKE :dlike"
            )
        sql = (
            "SELECT c.code AS code, c.name AS name, TRIM(COALESCE(c.ctype,'')) AS ctype, "
            "TRIM(COALESCE(c.mobile,'')) AS mobile, TRIM(COALESCE(c.telephone,'')) AS telephone, "
            "TRIM(COALESCE(c.city,'')) AS city FROM clients AS c "
            "WHERE (c.mobile LIKE :like OR c.telephone LIKE :like OR c.code LIKE :like "
            f"OR c.name LIKE :like{digit_clause}) ORDER BY c.name LIMIT 20"
        )
        return self.db.fetchall(sql, params)
