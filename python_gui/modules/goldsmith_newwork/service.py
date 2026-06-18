"""Goldsmith New-Work Note — port of GoldsmithNewWorkNoteController.

A worklist in ``smithnewwrk`` of items handed to a goldsmith, with a status
(1 = new work, 2 = work-in-progress, 3 = finished). ``save`` applies a grid
edit: delete listed ids, upsert rows by ``sno`` (a blank smithcode deletes the
row), then sweep any rows left with a blank smithcode.
"""

from __future__ import annotations

from datetime import date, datetime

from ...core.db import Database

_VALID_STATUS = (1, 2, 3)
_TYPE_STATUS = {"new-work": 1, "work-in-progress": 2, "work-finished": 3}


def _norm_date(v: str) -> str:
    v = str(v or "").strip()
    if not v:
        return date.today().isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(v[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return date.today().isoformat()


def _status(v) -> int:
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 1
    return v if v in _VALID_STATUS else 1


class GoldsmithNewWorkService:
    def __init__(self, database: Database):
        self.db = database

    def list(self, type_: str = "", smithcode: str = "") -> list[dict]:
        if not self.db.table_exists("smithnewwrk"):
            return []
        sname = "c.name" if self.db.table_exists("clients") else "''"
        iname = "i.name" if self.db.table_exists("items") else "''"
        joins = ""
        if self.db.table_exists("clients"):
            joins += "LEFT JOIN clients c ON c.code = s.smithcode "
        if self.db.table_exists("items"):
            joins += "LEFT JOIN items i ON i.code = s.icode "
        where = ["1=1"]
        params: dict = {}
        if type_ == "pending":
            where.append("s.status <> 3")
        elif type_ in _TYPE_STATUS:
            where.append("s.status = :st"); params["st"] = _TYPE_STATUS[type_]
        if smithcode.strip():
            where.append("TRIM(COALESCE(s.smithcode,'')) = :sc"); params["sc"] = smithcode.strip().upper()
        return self.db.fetchall(
            f"SELECT s.sno, s.tdate, s.smithcode, s.ordno, s.icode, s.qty, s.weight, "
            f"s.part, s.status, TRIM(COALESCE({sname},'')) AS smithname, "
            f"TRIM(COALESCE({iname},'')) AS itemname FROM smithnewwrk s {joins}"
            f"WHERE {' AND '.join(where)} ORDER BY s.tdate, s.smithcode, s.icode LIMIT 5000", params)

    def save(self, rows: list[dict], deleted_ids: list[int] | None = None) -> str:
        if not self.db.table_exists("smithnewwrk"):
            raise RuntimeError("Table smithnewwrk not found")
        deleted = [int(x) for x in (deleted_ids or []) if str(x).strip() and int(x) > 0]
        cols = set(self.db.columns("smithnewwrk"))
        with self.db.transaction() as tx:
            if deleted:
                ph = ", ".join(f":d{i}" for i in range(len(deleted)))
                tx.execute(f"DELETE FROM smithnewwrk WHERE sno IN ({ph})",
                           {f"d{i}": v for i, v in enumerate(deleted)})
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sno = int(row.get("sno") or 0)
                smithcode = str(row.get("smithcode") or "").strip().upper()
                data = {
                    "smithcode": smithcode, "tdate": _norm_date(row.get("tdate")),
                    "ordno": str(row.get("ordno") or "").strip().upper(),
                    "icode": str(row.get("icode") or "").strip().upper(),
                    "qty": int(row.get("qty") or 0), "weight": float(row.get("weight") or 0),
                    "part": str(row.get("part") or "").strip(), "status": _status(row.get("status", 1)),
                }
                data = {k: v for k, v in data.items() if k in cols}
                if sno > 0:
                    if smithcode == "":
                        tx.execute("DELETE FROM smithnewwrk WHERE sno = :s", {"s": sno})
                    else:
                        sets = ", ".join(f"{k} = :{k}" for k in data)
                        tx.execute(f"UPDATE smithnewwrk SET {sets} WHERE sno = :sno", {**data, "sno": sno})
                elif smithcode != "":
                    names = ", ".join(data); binds = ", ".join(f":{k}" for k in data)
                    tx.execute(f"INSERT INTO smithnewwrk ({names}) VALUES ({binds})", data)
            tx.execute("DELETE FROM smithnewwrk WHERE smithcode IS NULL OR TRIM(COALESCE(smithcode,'')) = ''")
        return "Updation Completed..."

    def delete(self, sno: int) -> str:
        if not self.db.table_exists("smithnewwrk"):
            raise RuntimeError("Table smithnewwrk not found")
        sno = int(sno)
        if sno <= 0:
            raise ValueError("Invalid sno")
        self.db.execute("DELETE FROM smithnewwrk WHERE sno = :s", {"s": sno})
        return "Deleted"
