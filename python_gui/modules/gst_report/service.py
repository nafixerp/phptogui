"""GST summary (read-only) — outward tax from the daybook tax heads.

The `sales_bills` GSTR source table used by GstrReportController may not exist on
the legacy `demo` schema, so this computes the GST outward summary from the
posted daybook tax heads (SGST/CGST/IGST credits) and the RS sales base over a
date range (control <= gilevel). Tax heads are positive (credit) in daybook.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money


class GstSummaryService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = int(gilevel or 1)

    def _head_total(self, accode: str, date_from: str, date_to: str) -> Decimal:
        v = self.db.scalar(
            "SELECT COALESCE(SUM(amount), 0) FROM daybook "
            "WHERE TRIM(accode) = :a AND tdate BETWEEN :f AND :t AND control <= :g",
            {"a": accode, "f": date_from, "t": date_to, "g": self.gilevel},
        )
        return money(v)

    def summary(self, date_from: str, date_to: str) -> dict:
        if not self.db.table_exists("daybook"):
            return {"taxable": Decimal("0"), "sgst": Decimal("0"), "cgst": Decimal("0"),
                    "igst": Decimal("0"), "total_tax": Decimal("0")}
        sgst = self._head_total("SGST", date_from, date_to)
        cgst = self._head_total("CGST", date_from, date_to)
        igst = self._head_total("IGST", date_from, date_to)
        # RS sales base is credit (positive); present as a positive taxable value
        taxable = self._head_total("RS", date_from, date_to)
        return {
            "taxable": taxable,
            "sgst": sgst, "cgst": cgst, "igst": igst,
            "total_tax": money(sgst + cgst + igst),
        }
