"""Barcode Entry rules — port of BarcodeEntryController save/delete/buildBarcodeRow.

PowerBuilder compatibility quirks reproduced:
  * sold='Y' is stored as stk='N' (else 'Y').
  * nodisc='Y' is stored as '' ... wait: nodisc='Y' -> stored 'N', else ''.
  * stkinnos 'Y'/'N'; status always 'N'.
Row is column-filtered to the live `barcode` schema. Next barcode number =
max(bcode)+1 (BCMaxNo='Y', the default) or generali.BCNO+1, minimum 100001.
Delete blocked when the barcode appears in salesd (already sold).
(Diamond/stone detail tables are a documented follow-on.)
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import to_decimal
from .repo import BarcodeRepo

_FLOAT = ["qty", "weight", "stweight", "stprice", "wastage", "mc", "mcrate", "rate",
         "cost", "vap", "minvap", "tamt", "transtouch", "stktouch", "grate", "costmc",
         "coststone", "costperc", "smithmcrate"]
_TEXT = ["icode", "docno", "smithcode", "smcode", "qtype", "qunit", "serialno", "huid",
        "model", "subgrp", "part", "counter"]


class BarcodeError(Exception):
    pass


class BarcodeService:
    def __init__(self, repo: BarcodeRepo, session: AppSession | None = None, bc_max_no: str = "Y"):
        self.repo = repo
        self.session = session
        self.bc_max_no = (bc_max_no or "Y").strip().upper()

    def next_barcode(self) -> int:
        nxt = self.repo.max_bcode() if self.bc_max_no == "Y" else self.repo.generali_bcno()
        return nxt + 1 if nxt > 0 else 100001

    def get(self, bcode: int) -> dict | None:
        return self.repo.get(int(bcode))

    def load_item(self, icode: str) -> dict | None:
        return self.repo.load_item(icode)

    def search(self, term: str = "") -> list[dict]:
        return self.repo.search(term.strip())

    def build_row(self, data: dict) -> dict:
        def f(k):
            return to_decimal(data.get(k, 0)) or Decimal("0")

        row = {"bcode": int(to_decimal(data.get("bcode", 0)) or 0),
               "tdate": str(data.get("tdate") or "").strip() or None,
               "control": int(to_decimal(data.get("control", 0)) or 0),
               "status": "N"}
        for k in _FLOAT:
            row[k] = f(k)
        for k in _TEXT:
            row[k] = str(data.get(k) or "").strip()
        # special-mapped columns
        row["costamt"] = f("purchaseamt") if data.get("purchaseamt") not in (None, "") else f("costamt")
        row["sizemodel"] = str(data.get("size") or data.get("sizemodel") or "").strip()
        row["weight2"] = f("stickerwgt") if data.get("stickerwgt") not in (None, "") else f("weight2")
        # PB compatibility flags
        row["stk"] = "N" if str(data.get("sold") or "").strip().upper() == "Y" else "Y"
        row["stkinnos"] = "Y" if str(data.get("stkinnos") or "N").strip().upper() == "Y" else "N"
        row["nodisc"] = "N" if str(data.get("nodisc") or "").strip().upper() == "Y" else ""
        return self.repo.filter_columns(row)

    def save(self, data: dict, mode: str) -> dict:
        mode = str(mode or "").strip().lower()
        if mode in ("a", "add"):
            mode = "add"
        elif mode in ("e", "edit"):
            mode = "edit"
        if mode not in ("add", "edit"):
            raise BarcodeError('Invalid mode. Use "add" or "edit".')
        bcode = int(to_decimal(data.get("bcode", 0)) or 0)
        icode = str(data.get("icode") or "").strip()
        qty = to_decimal(data.get("qty", 0)) or Decimal("0")
        if bcode <= 0:
            raise BarcodeError("Barcode number is required")
        if icode == "":
            raise BarcodeError("Item code is required")
        if qty <= 0:
            raise BarcodeError("Quantity must be greater than zero")
        if not self.repo.has_table():
            raise BarcodeError("barcode table not found")

        exists = self.repo.exists(bcode)
        if mode == "add" and exists:
            raise BarcodeError(f"Barcode {bcode} already exists")
        if mode == "edit" and not exists:
            raise BarcodeError(f"Barcode {bcode} not found")

        row = self.build_row(data)
        if mode == "add":
            self.repo.insert(row)
            if self.bc_max_no == "N" and self.repo.db.table_exists("generali"):
                self.repo.set_bcno(bcode)
        else:
            self.repo.update(bcode, row)
        log_delpart(self.repo.db, self.session, f"Barcode({bcode}) {'Added' if mode == 'add' else 'Updated'}",
                    utype="A" if mode == "add" else "E", ttype="R")
        return {"bcode": bcode, "message": f"Barcode {'added' if mode == 'add' else 'updated'} successfully"}

    def delete(self, bcode: int) -> str:
        bcode = int(to_decimal(bcode) or 0)
        if bcode <= 0:
            raise BarcodeError("Invalid barcode number")
        if not self.repo.get(bcode):
            raise BarcodeError("Barcode not found")
        if self.repo.sold(bcode):
            raise BarcodeError("This barcode is already sold. You cannot delete it")
        self.repo.delete(bcode)
        log_delpart(self.repo.db, self.session, f"Barcode({bcode}) Deleted", utype="D", ttype="R")
        return "Barcode deleted successfully"
