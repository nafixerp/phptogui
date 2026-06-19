"""Sales Bill Print — port of ``SalesBillPrintController::show`` (data + PDF).

Gathers a sales bill (``salesm`` header + ``salesd`` items) with customer,
salesman and state names, computes per-row net weight + line totals and the GST
split, then renders a PDF via :mod:`core.pdf`. The Laravel controller's many
print-layout INI toggles are presentation-only and are intentionally dropped —
this reproduces the *document content*, not the thermal-printer pixel layout.
"""

from __future__ import annotations

from decimal import Decimal

from ...core import printing
from ...core.db import Database
from ...core.decimals import money, to_decimal, weight
from ...core.pdf import build_document, format_money


class SalesBillPrintError(Exception):
    pass


class SalesBillPrintService:
    def __init__(self, database: Database):
        self.db = database

    def gather(self, slno: int) -> dict:
        """Collect everything needed to render the bill for ``salesm.slno``."""
        if not self.db.table_exists("salesm"):
            raise SalesBillPrintError("Sales table not found")
        master = self.db.fetchone("SELECT * FROM salesm WHERE slno = :s", {"s": int(slno)})
        if not master:
            raise SalesBillPrintError(f"Bill not found for slno: {slno}")

        details = self.db.fetchall(
            "SELECT * FROM salesd WHERE slno = :s ORDER BY sno", {"s": int(slno)}) \
            if self.db.table_exists("salesd") else []

        # item names for any blank detail name
        item_names: dict[str, str] = {}
        codes = sorted({str(d.get("code") or "").strip() for d in details if str(d.get("code") or "").strip()})
        if codes and self.db.table_exists("items"):
            ph = ", ".join(f":c{i}" for i in range(len(codes)))
            for r in self.db.fetchall(f"SELECT code, name FROM items WHERE code IN ({ph})",
                                      {f"c{i}": v for i, v in enumerate(codes)}):
                item_names[str(r["code"]).strip()] = str(r.get("name") or "").strip()

        cust = printing.party_info(self.db, master.get("custcode"))
        sman = printing.lookup_name(self.db, "sman", master.get("smcode"))
        state = printing.lookup_name(self.db, "state", master.get("statecode"))

        rows = []
        for i, d in enumerate(details, start=1):
            w = to_decimal(d.get("weight"))
            sw = to_decimal(d.get("stonewgt"))
            name = str(d.get("name") or "").strip() or item_names.get(str(d.get("code") or "").strip(), "")
            rows.append({
                "sno": d.get("sno") or i,
                "code": str(d.get("code") or "").strip(),
                "name": name,
                "qty": int(to_decimal(d.get("qty"))),
                "weight": weight(w),
                "stonewgt": weight(sw),
                "netwgt": weight(max(w - sw, Decimal("0"))),
                "rate": money(d.get("rate")),
                "mcharge": money(d.get("mcharge")),
                "amount": money(d.get("amount")),
            })

        totals = printing.sum_columns(details, {
            "qty": "qty", "weight": "weight", "stonewgt": "stonewgt",
            "mcharge": "mcharge", "amount": "amount"})

        billamt = money(master.get("billamt"))
        netamt = money(master.get("netamt"))
        staxamt = money(master.get("staxamt"))
        gst = printing.gst_split(staxamt, master.get("staxperc"), master.get("cst") or "N",
                                 base_amt=billamt, net_amt=netamt)

        return {
            "master": master, "rows": rows, "row_totals": totals,
            "customer": cust, "customer_address": printing.address_line(cust),
            "salesman": sman, "state": state,
            "billno": str(master.get("billno") or "").strip(),
            "tdate": str(master.get("tdate") or "").strip(),
            "billamt": billamt, "netamt": netamt, "staxamt": staxamt,
            "discount": money(master.get("discount")), "round": money(master.get("round")),
            "ramt": money(master.get("ramt")), "gst": gst,
            "company": printing.company_info(self.db),
            "title": "Tax Invoice" if int(to_decimal(master.get("control")) or 1) == 1 else "Estimate",
        }

    def render_pdf(self, slno: int, path: str) -> str:
        data = self.gather(slno)
        shop = {"name": data["company"]["name"], "address": data["company"]["address"],
                "phone": data["company"]["phone"], "gst": data["company"]["gst"]}
        details = [
            ("Bill No", data["billno"]), ("Date", data["tdate"]),
            ("Customer", str(data["master"].get("custname") or "").strip()),
            ("Address", data["customer_address"]),
        ]
        if data["salesman"]:
            details.append(("Salesman", data["salesman"]))
        item_cols = [("sno", "#"), ("name", "Item"), ("qty", "Qty"),
                     ("netwgt", "Net Wt"), ("rate", "Rate"), ("amount", "Amount")]
        items = [{**r, "weight": str(r["weight"]), "netwgt": str(r["netwgt"]),
                  "rate": str(r["rate"]), "amount": str(r["amount"])} for r in data["rows"]]
        totals = [("Bill Amount", format_money(data["billamt"]))]
        if data["discount"] > 0:
            totals.append(("Discount", format_money(data["discount"])))
        if data["gst"]["is_igst"]:
            if data["gst"]["igst"] > 0:
                totals.append((data["gst"]["igst_label"], format_money(data["gst"]["igst"])))
        else:
            if data["gst"]["cgst"] > 0:
                totals.append((data["gst"]["cgst_label"], format_money(data["gst"]["cgst"])))
                totals.append((data["gst"]["sgst_label"], format_money(data["gst"]["sgst"])))
        if data["round"] != 0:
            totals.append(("Round Off", format_money(data["round"])))
        totals.append(("Net Amount", format_money(data["netamt"])))
        return build_document(path, title=data["title"], shop=shop, details=details,
                              items=items, item_columns=item_cols, totals=totals)
