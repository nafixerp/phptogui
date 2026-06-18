"""Barcode Multi-Entry — port of BarcodeMultiEntryController.

Bulk creation/update of `barcode` rows (one barcoded piece per row). All rows
in a batch share a reserved ``rslno`` (SERIALNO) and a ``BC/NNNNNN`` document
number (BCDOCNO counter). Each row is upserted by ``bcode`` (column-filtered to
the live schema), ``stk='Y'``, and the ``BCNO`` counter is advanced to the
highest bcode used. This is a stock-master entry — no daybook posting.

Secondary-DB mirroring is a documented follow-on (SecondaryDatabaseSync).
"""

from __future__ import annotations

from datetime import date

from ...core.auth import AppSession
from ...core.db import Database
from ...core.decimals import money, weight as wq
from ...core.posting import PostingEngine


class BarcodeMultiError(Exception):
    pass


class BarcodeMultiService:
    def __init__(self, engine: PostingEngine, session: AppSession | None = None, control: int = 1):
        self.pe = engine
        self.db = engine.db
        self.session = session
        self.control = int(control or 1)

    def next_barcode(self) -> int:
        nxt = 0
        if self.db.table_exists("barcode"):
            nxt = int(self.db.scalar("SELECT COALESCE(MAX(bcode),0) FROM barcode") or 0)
        if nxt <= 0 and self.db.table_exists("generali"):
            nxt = int(self.db.scalar("SELECT cvalue FROM generali WHERE code='BCNO'") or 0)
        if nxt <= 0:
            nxt = 1_000_000
        return nxt + 1

    def next_doc_no(self) -> str:
        cur = 0
        if self.db.table_exists("generali"):
            cur = int(self.db.scalar("SELECT cvalue FROM generali WHERE code='BCDOCNO'") or 0)
        return f"BC/{cur + 1:06d}"

    def save(self, rows: list[dict], tdate: str | None = None, smcode: str = "",
             smithcode: str = "") -> dict:
        if not rows:
            raise BarcodeMultiError("No rows to save")
        if not self.db.table_exists("barcode"):
            raise BarcodeMultiError("Barcode table missing")
        tdate = tdate or date.today().isoformat()
        cols = set(self.db.columns("barcode"))
        saved = 0
        with self.db.transaction() as tx:
            rslno = self.pe.next_serial_no(tx)
            docno = f"BC/{self.pe.increment_gen_int(tx, 'BCDOCNO'):06d}"
            max_bcode = 0
            for row in rows:
                bcode = int(row.get("barcode") or row.get("bcode") or 0)
                icode = str(row.get("itemcode") or row.get("icode") or "").strip().upper()
                weight = wq(row.get("weight"))
                if bcode <= 0 or icode == "" or weight <= 0:
                    continue
                stickerwgt = wq(row.get("stickerwgt"))
                data = {
                    "bcode": bcode, "icode": icode, "qty": int(row.get("qty") or 1),
                    "weight": weight, "stweight": wq(row.get("stwgt")),
                    "stprice": money(row.get("stprice")), "wastage": wq(row.get("wastage")),
                    "mc": money(row.get("mcamt")), "tdate": tdate, "smcode": smcode,
                    "control": self.control, "mcrate": money(row.get("mcrate")),
                    "rslno": rslno, "islno": 0, "stk": "Y", "rate": 0,
                    "smithmcrate": money(row.get("smithmcrate")), "weight2": wq(weight + stickerwgt),
                    "vap": money(row.get("vaperc")), "sizemodel": str(row.get("size") or "").strip().upper(),
                    "model": str(row.get("model") or "").strip().upper(), "counter": "",
                    "subgrp": str(row.get("subgrp") or "").strip(), "minvap": money(row.get("minvap")),
                    "stkinnos": "N", "docno": docno, "status": "N", "smithcode": smithcode,
                }
                huid = str(row.get("huid") or "").strip().upper()
                if huid:
                    data["huid"] = huid
                use = {k: v for k, v in data.items() if k in cols}
                exists = tx.fetchall("SELECT 1 FROM barcode WHERE bcode = :b LIMIT 1", {"b": bcode})
                if exists:
                    sets = ", ".join(f"{k} = :{k}" for k in use if k != "bcode")
                    tx.execute(f"UPDATE barcode SET {sets} WHERE bcode = :bcode", use)
                else:
                    names = ", ".join(use); binds = ", ".join(f":{k}" for k in use)
                    tx.execute(f"INSERT INTO barcode ({names}) VALUES ({binds})", use)
                max_bcode = max(max_bcode, bcode)
                saved += 1
            if max_bcode > 0 and self.db.table_exists("generali"):
                cur = int(tx.scalar("SELECT COALESCE((SELECT cvalue FROM generali WHERE code='BCNO'),0)") or 0)
                if max_bcode > cur:
                    exists = tx.fetchall("SELECT 1 FROM generali WHERE code='BCNO' LIMIT 1")
                    if exists:
                        tx.execute("UPDATE generali SET cvalue = :v WHERE code='BCNO'", {"v": max_bcode})
                    else:
                        tx.execute("INSERT INTO generali (code, cvalue) VALUES ('BCNO', :v)", {"v": max_bcode})
        if saved == 0:
            raise BarcodeMultiError("No valid rows to save")
        return {"saved": saved, "docno": docno, "rslno": rslno}
