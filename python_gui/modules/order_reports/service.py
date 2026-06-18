"""Order reports — Process / Returns / Pending Register / Advance Report.

- ``pending_process``: open orders (``orderm.status = 1``) with total advance
  and customer mobile. Port of OrderProcessController.
- ``returns``: orders billed out (orderm.salebill -> salesm.billno) over a
  sale-date range. Port of OrderReturnsController.
- ``pending_register``: item-level pending orders (orderm+orderd+items,
  status=1). Port of OrderPendingRegisterController.
- ``advance_report``: orders in a date range with advance components and
  advafter top-ups; total advance = advance+eamt+sretamt+advaft. Port of
  OrderAdvanceReportController.
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import money, weight as wq

PENDING_STATUS = 1
RETURNED_STATUS = 2


class OrderReportsService:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.gilevel = max(1, int(gilevel or 1))

    def _col(self, t: str, c: str) -> bool:
        return self.db.table_exists(t) and self.db.column_exists(t, c)

    def pending_process(self) -> list[dict]:
        if not self.db.table_exists("orderm"):
            return []
        rows = self.db.fetchall(
            "SELECT slno, TRIM(ordno) AS ordno, tdate, duedate, custcode, "
            "TRIM(COALESCE(custname,'')) AS custname, COALESCE(billamt,0) AS billamt, "
            "COALESCE(advance,0) AS advance, COALESCE(eamt,0) AS eamt, "
            "COALESCE(sretamt,0) AS sretamt "
            "FROM orderm WHERE control <= :g AND status = :s ORDER BY slno",
            {"g": self.gilevel, "s": PENDING_STATUS})
        mobiles = {}
        if self.db.table_exists("clients") and rows:
            codes = sorted({str(r.get("custcode") or "").strip() for r in rows if r.get("custcode")})
            if codes:
                ph = ", ".join(f":c{i}" for i in range(len(codes)))
                mr = self.db.fetchall(
                    f"SELECT TRIM(code) AS code, mobile FROM clients WHERE TRIM(code) IN ({ph})",
                    {f"c{i}": v for i, v in enumerate(codes)})
                mobiles = {r["code"]: str(r.get("mobile") or "").strip() for r in mr}
        out = []
        for r in rows:
            tadv = money(money(r["advance"]) + money(r["eamt"]) + money(r["sretamt"]))
            out.append({
                "ordno": str(r["ordno"]), "tdate": str(r.get("tdate") or ""),
                "duedate": str(r.get("duedate") or ""), "custname": str(r["custname"]),
                "billamt": money(r["billamt"]), "tadv": tadv,
                "mobile": mobiles.get(str(r.get("custcode") or "").strip(), ""),
            })
        return out

    def returns(self, date1: str, date2: str) -> list[dict]:
        if not (self.db.table_exists("orderm") and self.db.table_exists("salesm")):
            return []
        return self.db.fetchall(
            "SELECT TRIM(orderm.ordno) AS ordno, orderm.tdate AS ord_tdate, orderm.duedate, "
            "TRIM(COALESCE(orderm.custname,'')) AS custname, COALESCE(orderm.billamt,0) AS ord_billamt, "
            "COALESCE(orderm.advance,0) AS ord_advance, orderm.smcode, "
            "salesm.billno AS salebill, salesm.tdate AS sale_tdate, COALESCE(salesm.billamt,0) AS sale_billamt "
            "FROM orderm JOIN salesm ON orderm.salebill = salesm.billno "
            "WHERE orderm.control <= :g AND salesm.tdate BETWEEN :f AND :t "
            "ORDER BY orderm.tdate LIMIT 2000",
            {"g": self.gilevel, "f": date1, "t": date2})

    def pending_register(self, smcode: str = "", itemcode: str = "") -> list[dict]:
        if not (self.db.table_exists("orderm") and self.db.table_exists("orderd")
                and self.db.table_exists("items")):
            return []
        where = ["orderm.control <= :g", "orderm.status = :s"]
        params: dict = {"g": self.gilevel, "s": PENDING_STATUS}
        if smcode.strip() and self._col("orderm", "smcode"):
            where.append("orderm.smcode = :sm"); params["sm"] = smcode.strip()
        if itemcode.strip():
            where.append("orderd.code = :ic"); params["ic"] = itemcode.strip()
        rows = self.db.fetchall(
            "SELECT TRIM(orderm.ordno) AS ordno, orderm.tdate, orderm.duedate, "
            "TRIM(COALESCE(orderm.custname,'')) AS custname, orderm.smcode, "
            "COALESCE(orderm.advance,0) AS advance, TRIM(items.name) AS itemname, "
            "TRIM(orderd.code) AS itemcode, COALESCE(orderd.qty,0) AS qty, "
            "COALESCE(orderd.weight,0) AS weight, COALESCE(orderd.stonewgt,0) AS stonewgt "
            "FROM orderm JOIN orderd ON orderm.slno = orderd.slno "
            "JOIN items ON orderd.code = items.code "
            f"WHERE {' AND '.join(where)} ORDER BY orderm.duedate, orderm.ordno LIMIT 5000", params)
        return [{"ordno": str(r.get("ordno") or ""), "tdate": str(r.get("tdate") or ""),
                 "duedate": str(r.get("duedate") or ""), "custname": str(r.get("custname") or ""),
                 "itemname": str(r.get("itemname") or ""), "itemcode": str(r.get("itemcode") or ""),
                 "qty": int(r.get("qty") or 0), "weight": wq(r.get("weight")),
                 "stonewgt": wq(r.get("stonewgt")), "advance": money(r.get("advance"))} for r in rows]

    def advance_report(self, date1: str, date2: str, filter_: str = "All") -> dict:
        if not self.db.table_exists("orderm"):
            return {"rows": [], "totals": {"advance": money(0), "advaft": money(0), "totadv": money(0)}}
        where = ["control <= :g", "tdate BETWEEN :f AND :t"]
        params: dict = {"g": self.gilevel, "f": date1, "t": date2}
        if filter_ == "Pending":
            where.append("status = :st"); params["st"] = PENDING_STATUS
        elif filter_ == "Returned":
            where.append("status = :st"); params["st"] = RETURNED_STATUS
        rows = self.db.fetchall(
            "SELECT slno, TRIM(ordno) AS ordno, tdate, duedate, TRIM(COALESCE(custname,'')) AS custname, "
            "smcode, COALESCE(advance,0) AS advance, COALESCE(eamt,0) AS eamt, "
            "COALESCE(sretamt,0) AS sretamt, COALESCE(gadvance,0) AS gadvance, COALESCE(status,0) AS status "
            f"FROM orderm WHERE {' AND '.join(where)} ORDER BY tdate, slno LIMIT 5000", params)
        has_af = self.db.table_exists("advafter")
        out = []; t_adv = money(0); t_aft = money(0); t_tot = money(0)
        for r in rows:
            advaft = money(0)
            if has_af:
                advaft = money(self.db.scalar(
                    "SELECT COALESCE(SUM(amount),0) FROM advafter WHERE slno = :s", {"s": r["slno"]}))
            adv = money(r.get("advance")); eamt = money(r.get("eamt")); sret = money(r.get("sretamt"))
            totadv = money(adv + eamt + sret + advaft)
            out.append({"ordno": str(r.get("ordno") or ""), "tdate": str(r.get("tdate") or ""),
                        "custname": str(r.get("custname") or ""), "advance": adv, "eamt": eamt,
                        "sretamt": sret, "gadvance": wq(r.get("gadvance")), "advaft": advaft,
                        "totadv": totadv, "status": int(r.get("status") or 0)})
            t_adv += adv; t_aft += advaft; t_tot += totadv
        return {"rows": out, "totals": {"advance": t_adv, "advaft": t_aft, "totadv": t_tot}}
