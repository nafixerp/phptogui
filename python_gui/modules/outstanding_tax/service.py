"""Outstanding Tax Report — port of OutstandingTaxReportController::data.

Output tax (collected on sales) vs input tax (paid on purchases) over a period,
broken into SGST/CGST/IGST (+ TCS), with the net payable/refundable. Falls back
to ``staxamt`` for sales when the GST split columns are all zero.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.db import Database
from ...core.decimals import money

_ZERO = Decimal("0")


class OutstandingTaxService:
    def __init__(self, database: Database, rlevel: int = 1):
        self.db = database
        self.rlevel = max(1, int(rlevel or 1))

    def _col(self, t: str, c: str) -> bool:
        return self.db.table_exists(t) and self.db.column_exists(t, c)

    def _sum(self, table: str, date1: str, date2: str) -> dict:
        cols = ["COALESCE(SUM(COALESCE(sgst,0)),0) AS sgst",
                "COALESCE(SUM(COALESCE(cgst,0)),0) AS cgst",
                "COALESCE(SUM(COALESCE(igst,0)),0) AS igst"]
        if self._col(table, "staxamt"):
            cols.append("COALESCE(SUM(COALESCE(staxamt,0)),0) AS staxamt")
        if self._col(table, "tcsamt"):
            cols.append("COALESCE(SUM(COALESCE(tcsamt,0)),0) AS tcsamt")
        return self.db.fetchone(
            f"SELECT {', '.join(cols)} FROM {table} "
            "WHERE tdate BETWEEN :f AND :t AND control <= :g",
            {"f": date1, "t": date2, "g": self.rlevel}) or {}

    def report(self, date1: str, date2: str) -> dict:
        rows = []
        tot_in = _ZERO; tot_out = _ZERO

        if self.db.table_exists("salesm"):
            s = self._sum("salesm", date1, date2)
            sgst, cgst, igst = money(s.get("sgst")), money(s.get("cgst")), money(s.get("igst"))
            total = sgst + cgst + igst
            if total == 0:
                total = money(s.get("staxamt"))
            if sgst > 0:
                rows.append({"description": "Sales - SGST", "inputtax": _ZERO, "outputtax": sgst}); tot_out += sgst
            if cgst > 0:
                rows.append({"description": "Sales - CGST", "inputtax": _ZERO, "outputtax": cgst}); tot_out += cgst
            if igst > 0:
                rows.append({"description": "Sales - IGST", "inputtax": _ZERO, "outputtax": igst}); tot_out += igst
            if sgst == 0 and cgst == 0 and igst == 0 and total > 0:
                rows.append({"description": "Sales Tax", "inputtax": _ZERO, "outputtax": total}); tot_out += total
            tcs = money(s.get("tcsamt"))
            if tcs > 0:
                rows.append({"description": "Sales - TCS", "inputtax": _ZERO, "outputtax": tcs}); tot_out += tcs

        if self.db.table_exists("purchasem"):
            p = self._sum("purchasem", date1, date2)
            sgst, cgst, igst = money(p.get("sgst")), money(p.get("cgst")), money(p.get("igst"))
            if sgst > 0:
                rows.append({"description": "Purchase - SGST", "inputtax": sgst, "outputtax": _ZERO}); tot_in += sgst
            if cgst > 0:
                rows.append({"description": "Purchase - CGST", "inputtax": cgst, "outputtax": _ZERO}); tot_in += cgst
            if igst > 0:
                rows.append({"description": "Purchase - IGST", "inputtax": igst, "outputtax": _ZERO}); tot_in += igst
            tcs = money(p.get("tcsamt"))
            if tcs > 0:
                rows.append({"description": "Purchase - TCS", "inputtax": tcs, "outputtax": _ZERO}); tot_in += tcs

        net = money(tot_out - tot_in)
        return {"rows": rows, "total_input": money(tot_in), "total_output": money(tot_out),
                "net": net, "net_label": "Payable" if net >= 0 else "Refundable"}
