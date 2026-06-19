"""Sales Return Print — port of ``SalesReturnPrintController::show``.

Loads a sales-return (``salesrm`` + ``salesrd``, ``sr = 'R'``) by slno or
billno, builds per-row net weight + totals and the GST split, and computes the
refund/closing balance, then renders a PDF. Layout INI toggles are dropped
(presentation only); the document content is reproduced faithfully.
"""

from __future__ import annotations

from decimal import Decimal

from ...core import printing
from ...core.db import Database
from ...core.decimals import money, to_decimal, weight
from ...core.pdf import build_document, format_money


class SalesReturnPrintError(Exception):
    pass


class SalesReturnPrintService:
    def __init__(self, database: Database):
        self.db = database

    def gather(self, slno: int = 0, billno: str = "") -> dict:
        if not self.db.table_exists("salesrm"):
            raise SalesReturnPrintError("Sales return table not found")
        if int(slno or 0) > 0:
            master = self.db.fetchone("SELECT * FROM salesrm WHERE slno = :s", {"s": int(slno)})
        elif str(billno or "").strip():
            master = self.db.fetchone(
                "SELECT * FROM salesrm WHERE billno = :b AND sr = 'R' ORDER BY slno DESC LIMIT 1",
                {"b": str(billno).strip()})
        else:
            raise SalesReturnPrintError("No bill selected (give slno or billno)")
        if not master:
            raise SalesReturnPrintError("Sales return bill not found")
        slno = int(master["slno"])

        details = []
        if self.db.table_exists("salesrd"):
            details = self.db.fetchall(
                "SELECT rd.*, COALESCE(i.name,'') AS itemname2 FROM salesrd rd "
                "LEFT JOIN items i ON i.code = rd.code WHERE rd.slno = :s ORDER BY rd.sno",
                {"s": slno}) if self.db.table_exists("items") else self.db.fetchall(
                "SELECT * FROM salesrd WHERE slno = :s ORDER BY sno", {"s": slno})

        cust = printing.party_info(self.db, master.get("custcode"))
        sman = printing.lookup_name(self.db, "sman", master.get("smcode"))

        rows = []
        for i, d in enumerate(details, start=1):
            w = to_decimal(d.get("weight"))
            sw = to_decimal(d.get("stonewgt"))
            name = str(d.get("name") or "").strip() or str(d.get("itemname2") or "").strip() \
                or str(d.get("code") or "").strip()
            rows.append({
                "sno": d.get("sno") or i, "code": str(d.get("code") or "").strip(), "name": name,
                "qty": int(to_decimal(d.get("qty"))), "weight": weight(w),
                "stonewgt": weight(sw), "netwgt": weight(max(w - sw, Decimal("0"))),
                "rate": money(d.get("rate")), "amount": money(d.get("amount")),
            })

        totals = printing.sum_columns(details, {
            "qty": "qty", "weight": "weight", "stonewgt": "stonewgt", "amount": "amount"})

        billamt = money(master.get("billamt"))
        netamt = money(master.get("netamt"))
        pamt = money(master.get("pamt"))
        staxamt = money(master.get("staxamt"))
        ob = money(master.get("ob"))
        gst = printing.gst_split(staxamt, master.get("staxperc"), master.get("cst") or "N",
                                 base_amt=billamt, net_amt=netamt)
        refund = money(netamt - pamt)

        control = int(to_decimal(master.get("control")) or 1)
        return {
            "master": master, "rows": rows, "row_totals": totals,
            "customer": cust, "customer_address": printing.address_line(cust), "salesman": sman,
            "billno": str(master.get("billno") or "").strip(),
            "tdate": str(master.get("tdate") or "").strip(),
            "sbillno": str(master.get("sbillno") or "").strip(),
            "billamt": billamt, "netamt": netamt, "pamt": pamt, "staxamt": staxamt,
            "discount": money(master.get("discount")), "gst": gst,
            "refund": refund, "balance": refund, "closing_balance": money(ob + refund),
            "company": printing.company_info(self.db),
            "title": "Sales Return Invoice" if control == 1 else "Sales Return Estimate",
        }

    def render_pdf(self, slno: int = 0, billno: str = "", path: str = "") -> str:
        data = self.gather(slno, billno)
        comp = data["company"]
        shop = {"name": comp["name"], "address": comp["address"], "phone": comp["phone"], "gst": comp["gst"]}
        details = [("Bill No", data["billno"]), ("Date", data["tdate"]),
                   ("Customer", str(data["master"].get("custname") or "").strip()),
                   ("Address", data["customer_address"])]
        if data["sbillno"]:
            details.append(("Orig. Bill", data["sbillno"]))
        item_cols = [("sno", "#"), ("name", "Item"), ("qty", "Qty"),
                     ("netwgt", "Net Wt"), ("rate", "Rate"), ("amount", "Amount")]
        items = [{**r, "netwgt": str(r["netwgt"]), "rate": str(r["rate"]),
                  "amount": str(r["amount"])} for r in data["rows"]]
        totals = [("Bill Amount", format_money(data["billamt"]))]
        if not data["gst"]["is_igst"] and data["gst"]["cgst"] > 0:
            totals.append((data["gst"]["cgst_label"], format_money(data["gst"]["cgst"])))
            totals.append((data["gst"]["sgst_label"], format_money(data["gst"]["sgst"])))
        elif data["gst"]["is_igst"] and data["gst"]["igst"] > 0:
            totals.append((data["gst"]["igst_label"], format_money(data["gst"]["igst"])))
        totals.append(("Net Amount", format_money(data["netamt"])))
        totals.append(("Refund", format_money(data["refund"])))
        return build_document(path, title=data["title"], shop=shop, details=details,
                              items=items, item_columns=item_cols, totals=totals)
