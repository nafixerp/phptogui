"""Item Adjustment rules — port of ItemAdjustmentController::save.

A from->to transfer must be weight-neutral when both are real items:
fromwgt > 0, towgt > 0 and |fromwgt - towgt| <= 0.0001 (special code 'AL' =
add/less, exempt). Records an itemadj row and moves stock: from = negative,
to = positive (items + itemsstk).
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import to_decimal
from ...core.posting import PostingEngine
from .repo import ItemAdjustmentRepo


class ItemAdjustmentError(Exception):
    pass


class ItemAdjustmentService:
    def __init__(self, repo: ItemAdjustmentRepo, engine: PostingEngine,
                 session: AppSession | None = None, control: int = 1):
        self.repo = repo
        self.pe = engine
        self.session = session
        self.control = int(control or 1)

    def save(self, data: dict) -> dict:
        fromcode = str(data.get("fromcode") or "").strip().upper()
        tocode = str(data.get("tocode") or "").strip().upper()
        from_wgt = to_decimal(data.get("fromwgt", 0)) or Decimal("0")
        to_wgt = to_decimal(data.get("towgt", 0)) or Decimal("0")
        from_qty = int(to_decimal(data.get("fromqty", 0)) or 0)
        to_qty = int(to_decimal(data.get("toqty", 0)) or 0)
        from_stwgt = to_decimal(data.get("fromstwgt", 0)) or Decimal("0")
        to_stwgt = to_decimal(data.get("tostwgt", 0)) or Decimal("0")
        from_stktype = str(data.get("fromstktype") or "").strip()
        to_stktype = str(data.get("tostktype") or "").strip()

        if fromcode == "" or tocode == "":
            raise ItemAdjustmentError("From and To item codes are required")
        if fromcode != "AL" and not self.repo.item_exists(fromcode):
            raise ItemAdjustmentError(f"From item '{fromcode}' does not exist")
        if tocode != "AL" and not self.repo.item_exists(tocode):
            raise ItemAdjustmentError(f"To item '{tocode}' does not exist")
        if fromcode != "AL" and tocode != "AL":
            if from_wgt <= 0 or to_wgt <= 0 or abs(from_wgt - to_wgt) > Decimal("0.0001"):
                raise ItemAdjustmentError("From and To weights must be positive and equal")

        particular = str(data.get("particular") or f"Item adjusted from {fromcode} to {tocode}")

        with self.pe.db.transaction() as tx:
            slno = self.pe.next_serial_no(tx)
            self.repo.insert_itemadj(tx, {
                "slno": slno, "tdate": str(data.get("tdate") or ""),
                "fromcode": fromcode, "fromqty": from_qty, "fromwgt": from_wgt, "fromstwgt": from_stwgt,
                "tocode": tocode, "toqty": to_qty, "towgt": to_wgt, "tostwgt": to_stwgt,
                "fromstktype": from_stktype, "tostktype": to_stktype,
                "particular": particular[:100], "control": self.control, "sno": 1,
            })
            if fromcode != "AL":
                self.repo.adjust_stock(tx, fromcode, -from_qty, -from_wgt, -from_stwgt, from_stktype, self.control)
            if tocode != "AL":
                self.repo.adjust_stock(tx, tocode, to_qty, to_wgt, to_stwgt, to_stktype, self.control)

        log_delpart(self.pe.db, self.session, f"Item Adj {fromcode}->{tocode}", utype="A", ttype="T")
        return {"slno": slno, "message": "Adjustment saved"}
