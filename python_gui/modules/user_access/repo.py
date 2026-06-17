"""User Access repository — SQL on `userm` / `userd`.

Source: app/Http/Controllers/UserAccessController.php + App\\Models\\UserAccess /
UserPermission. Frozen schema: `userm(code CHAR(10) PK, name, pcode VARCHAR(15),
maxcredit, maxdisc, minvaperc, maxadjwgtbc, maxdiscperc)`, `userd(code, menuitem)`.

`userd.menuitem` rows are the user's permission/blocked entries that the login
flow reads (see core.auth.AppSession.blocked_items).
"""

from __future__ import annotations

from ...core.db import Database, Tx

_NUMERIC = ["maxcredit", "maxdisc", "maxdiscperc", "minvaperc", "maxadjwgtbc"]
_LIST_COLS = "code, name, maxdisc, maxcredit, minvaperc, maxdiscperc, maxadjwgtbc"


class UserAccessRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, table: str) -> bool:
        return self.db.table_exists(table)

    def list_users(self) -> list[dict]:
        return self.db.fetchall(f"SELECT {_LIST_COLS} FROM userm ORDER BY code")

    def get_user(self, code: str) -> dict | None:
        return self.db.fetchone(
            f"SELECT {_LIST_COLS} FROM userm WHERE UPPER(TRIM(code)) = :c LIMIT 1",
            {"c": code.strip().upper()},
        )

    def user_exists(self, code: str) -> bool:
        return self.db.fetchone(
            "SELECT 1 FROM userm WHERE UPPER(TRIM(code)) = :c LIMIT 1",
            {"c": code.strip().upper()},
        ) is not None

    def permission_list(self, code: str) -> list[str]:
        rows = self.db.fetchall(
            "SELECT menuitem FROM userd WHERE UPPER(TRIM(code)) = :c", {"c": code.strip().upper()}
        )
        return [str(r["menuitem"]).strip() for r in rows if r.get("menuitem") is not None]

    # -- writes (within caller transaction) ---------------------------------
    def insert_user(self, tx: Tx, payload: dict) -> None:
        cols = ", ".join(payload)
        binds = ", ".join(f":{k}" for k in payload)
        tx.execute(f"INSERT INTO userm ({cols}) VALUES ({binds})", payload)

    def update_user(self, tx: Tx, code: str, payload: dict) -> None:
        sets = ", ".join(f"{k} = :{k}" for k in payload)
        params = dict(payload)
        params["_code"] = code.strip().upper()
        tx.execute(f"UPDATE userm SET {sets} WHERE UPPER(TRIM(code)) = :_code", params)

    def sync_permissions(self, tx: Tx, code: str, items: list[str]) -> None:
        """Delete the user's userd rows and reinsert (UserAccess::syncPermissions)."""
        code_u = code.strip().upper()
        tx.execute("DELETE FROM userd WHERE UPPER(TRIM(code)) = :c", {"c": code_u})
        for item in items:
            menuitem = str(item or "").strip().upper()
            if menuitem == "":
                continue
            tx.execute("INSERT INTO userd (code, menuitem) VALUES (:c, :m)",
                       {"c": code_u, "m": menuitem})

    def delete_user(self, tx: Tx, code: str) -> None:
        code_u = code.strip().upper()
        tx.execute("DELETE FROM userd WHERE UPPER(TRIM(code)) = :c", {"c": code_u})
        if self.has_table("userhist"):
            tx.execute("DELETE FROM userhist WHERE UPPER(TRIM(code)) = :c", {"c": code_u})
        # user_company_access is auxiliary; only touch it if present (no auto-create)
        if self.has_table("user_company_access"):
            tx.execute("DELETE FROM user_company_access WHERE UPPER(TRIM(code)) = :c", {"c": code_u})
        tx.execute("DELETE FROM userm WHERE UPPER(TRIM(code)) = :c", {"c": code_u})
