"""Purity Testing — port of PurityTestingController::actionSave / list.

Records a purity-test certificate in `testdet` (customer, purity %/ct, received
weight, sample type, dates). New records reserve the ``SLNO`` counter and set
``BILLNO`` to the doc number; edits update by slno. Column-filtered to the live
schema.
"""

from __future__ import annotations

from datetime import date

from ...core.db import Database
from ...core.decimals import money, weight as wq


class PurityTestingError(Exception):
    pass


class PurityTestingService:
    def __init__(self, database: Database, control: int = 1):
        self.db = database
        self.control = int(control or 1)

    def list(self, date1: str = "", date2: str = "") -> list[dict]:
        if not self.db.table_exists("testdet"):
            return []
        where = ["1=1"]
        params: dict = {}
        if date1 and date2:
            where.append("tdate BETWEEN :f AND :t"); params.update(f=date1, t=date2)
        return self.db.fetchall(
            f"SELECT * FROM testdet WHERE {' AND '.join(where)} ORDER BY slno DESC LIMIT 2000", params)

    def next_doc_no(self) -> int:
        if not self.db.table_exists("generali"):
            return 1
        return int(self.db.scalar("SELECT cvalue FROM generali WHERE code='BILLNO'") or 0) + 1

    def save(self, data: dict, edit_slno: int = 0) -> dict:
        if not self.db.table_exists("testdet"):
            raise PurityTestingError("testdet table not found")
        customer = str(data.get("customer") or "").strip()
        if not customer:
            raise PurityTestingError("Customer is required")
        cols = set(self.db.columns("testdet"))
        row = {
            "docno": str(data.get("docno") or "").strip(),
            "tdate": str(data.get("tdate") or "").strip() or date.today().isoformat(),
            "customer": customer, "purityinperc": wq(data.get("purityinperc")),
            "purityinct": wq(data.get("purityinct")),
            "otherinfo": str(data.get("otherinfo") or "").strip()[:40],
            "rcvdon": str(data.get("rcvdon") or "").strip() or None,
            "testedon": str(data.get("testedon") or "").strip() or None,
            "rcvdwgt": wq(data.get("rcvdwgt")),
            "typeofsample": str(data.get("typeofsample") or "").strip()[:40],
            "control": self.control,
        }
        with self.db.transaction() as tx:
            if int(edit_slno) > 0:
                use = {k: v for k, v in row.items() if k in cols}
                sets = ", ".join(f"{k} = :{k}" for k in use)
                tx.execute(f"UPDATE testdet SET {sets} WHERE slno = :slno", {**use, "slno": int(edit_slno)})
                return {"slno": int(edit_slno), "updated": True}
            # new: reserve SLNO + set BILLNO
            slno = self._counter(tx, "SLNO", increment=True)
            docno = row.get("docno") or ""
            if self.db.table_exists("generali") and str(docno).isdigit():
                self._set_generali(tx, "BILLNO", int(docno))
            use = {"slno": slno, **{k: v for k, v in row.items() if k in cols}}
            names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
            tx.execute(f"INSERT INTO testdet ({names}) VALUES ({binds})", use)
        return {"slno": slno, "updated": False}

    def _counter(self, tx, code: str, increment: bool = False) -> int:
        if not self.db.table_exists("generali"):
            return 1
        cur = int(tx.scalar("SELECT COALESCE((SELECT cvalue FROM generali WHERE code=:c),0)", {"c": code}) or 0)
        nxt = cur + 1 if increment else cur
        self._set_generali(tx, code, nxt)
        return nxt

    def _set_generali(self, tx, code: str, value: int) -> None:
        exists = tx.fetchall("SELECT 1 FROM generali WHERE code=:c LIMIT 1", {"c": code})
        if exists:
            tx.execute("UPDATE generali SET cvalue=:v WHERE code=:c", {"v": value, "c": code})
        else:
            tx.execute("INSERT INTO generali (code, cvalue) VALUES (:c, :v)", {"c": code, "v": value})
