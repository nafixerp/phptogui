"""Delpart audit log — port of Concerns/LogsDelpartAudit.

Many master/transaction controllers record add/edit/delete actions into the
`delpart` table. Source: app/Http/Controllers/Concerns/LogsDelpartAudit.php.

delpart schema (frozen): part VARCHAR(60), control TINYINT, tdate DATE,
slno DECIMAL, utype CHAR(1), ttype CHAR(2), updtdate DATE, updttime TIME,
uid CHAR(10), ic VARCHAR(5).

Rules replicated from the trait:
  * No-op if the `delpart` table is missing or `part` is empty.
  * `part` truncated to 60 chars; `control` = session semi/control/gilevel,
    numeric else 1 (desktop has no such session keys -> default 1).
  * `uid` = user_code, `ic` = user_code (trait falls back user_id->user_code).
  * Payload filtered to columns that actually exist before INSERT.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid import cycle / GUI-free import
    from .auth import AppSession
    from .db import Database


def log_delpart(
    database: "Database",
    session: "AppSession | None",
    part: str,
    *,
    utype: str = "E",
    ttype: str = "M",
    control: int | None = None,
    slno: int | None = None,
    tdate: str | None = None,
) -> None:
    try:
        if not database.table_exists("delpart"):
            return
        part = (part or "").strip()
        if part == "":
            return

        uid = (session.user_code if session else "").strip()
        ic = uid
        ctrl = control if isinstance(control, int) else 1

        payload = {
            "tdate": (tdate or date.today().isoformat()),
            "part": part[:60],
            "control": ctrl,
            "slno": slno,
            "utype": (utype or "E").strip().upper()[:1],
            "ttype": (ttype or "M").strip().upper()[:2],
            "updtdate": date.today().isoformat(),
            "updttime": datetime.now().strftime("%H:%M:%S"),
            "uid": uid,
            "ic": ic,
        }

        existing = set(database.columns("delpart"))
        filtered = {k: v for k, v in payload.items() if v is not None and k.lower() in existing}
        if not filtered:
            return
        names = ", ".join(filtered)
        binds = ", ".join(f":{k}" for k in filtered)
        database.execute(f"INSERT INTO delpart ({names}) VALUES ({binds})", filtered)
    except Exception:
        pass  # auditing must never break the operation it records
