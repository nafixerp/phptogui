"""Purchase Bill Print — port of ``PurchaseBillPrintController::show``.

Loads a purchase bill (``purchasem`` where ``pr = 'P'``, by slno or docno) with
its ``purchased`` items and ``purchaserd`` exchange rows, computes per-row net
weight, the supplier/salesman/state lookups and the GST split (which here can be
reconstructed from ``taxamt`` when the cgst/sgst/igst columns are blank), then
renders a PDF.
"""

from __future__ import annotations

from decimal import Decimal

from ...core import printing
from ...core.db import Database
from ...core.decimals import money, to_decimal, weight
from ...core.pdf import build_document, format_money


class PurchaseBillPrintError(Exception):
    pass


class PurchaseBillPrintService:
    def __init__(self, database: Database):
        self.db = database

    def _net_weight(self, d: dict) -> Decimal:
        nw = d.get("netwgt")
        if nw not in (None, ""):
            return weight(nw)
        return weight(to_decimal(d.get("weight")) - to_decimal(d.get("stwgt"))
                      - to_decimal(d.get("lesswgt")) - to_decimal(d.get("mud")))

    def gather(self, slno: int = 0, doc_no: str = "") -> dict:
        if not self.db.table_exists("purchasem"):
            raise PurchaseBillPrintError("Purchase table not found")
        if int(slno or 0) > 0:
            master = self.db.fetchone("SELECT * FROM purchasem WHERE pr = 'P' AND slno = :s", {"s": int(slno)})
        elif str(doc_no or "").strip():
            master = self.db.fetchone("SELECT * FROM purchasem WHERE pr = 'P' AND docno = :d",
                                      {"d": str(doc_no).strip()})
        else:
            raise PurchaseBillPrintError("No purchase bill selected")
        if not master:
            raise PurchaseBillPrintError("Purchase bill not found")
        slno = int(master["slno"])

        details = self.db.fetchall("SELECT * FROM purchased WHERE slno = :s ORDER BY sno", {"s": slno}) \
            if self.db.table_exists("purchased") else []
        exchange = self.db.fetchall("SELECT * FROM purchaserd WHERE slno = :s ORDER BY sno", {"s": slno}) \
            if self.db.table_exists("purchaserd") else []

        item_names: dict[str, str] = {}
        codes = sorted({str(r.get("code") or "").strip()
                        for r in (details + exchange) if str(r.get("code") or "").strip()})
        if codes and self.db.table_exists("items"):
            ph = ", ".join(f":c{i}" for i in range(len(codes)))
            for r in self.db.fetchall(f"SELECT code, name FROM items WHERE code IN ({ph})",
                                      {f"c{i}": v for i, v in enumerate(codes)}):
                item_names[str(r["code"]).strip()] = str(r.get("name") or "").strip()

        supplier = printing.party_info(self.db, master.get("suppcode"))
        sman = printing.lookup_name(self.db, "sman", master.get("smcode"))

        rows = []
        for i, d in enumerate(details, start=1):
            name = str(d.get("name") or "").strip() or item_names.get(str(d.get("code") or "").strip(), "")
            rows.append({
                "sno": i, "code": str(d.get("code") or "").strip(), "name": name,
                "purity": str(d.get("iqtype") or "").strip(),
                "qty": int(to_decimal(d.get("qty"))), "weight": weight(d.get("weight")),
                "stonewgt": weight(d.get("stwgt")), "netwgt": self._net_weight(d),
                "rate": money(d.get("rate")), "mcharge": money(d.get("mcharge")),
                "amount": money(d.get("amount")),
            })

        totals = printing.sum_columns(details, {
            "qty": "qty", "weight": "weight", "amount": "amount"})

        # GST split: prefer stored cgst/sgst/igst, else reconstruct from taxamt.
        taxamt = money(master.get("taxamt"))
        cgst = money(master.get("cgst"))
        sgst = money(master.get("sgst"))
        igst = money(master.get("igst"))
        if cgst <= 0 and sgst <= 0 and igst <= 0 and taxamt > 0:
            if str(master.get("cst") or "N").strip().upper() == "Y":
                igst = taxamt
            else:
                cgst = money(taxamt / 2)
                sgst = money(taxamt / 2)

        paid = money(master.get("pamt"))
        bal = master.get("bal")
        balance = money(bal) if bal not in (None, "") else money(money(master.get("netamt")) - paid)

        return {
            "master": master, "rows": rows, "exchange": exchange, "row_totals": totals,
            "supplier": supplier, "supplier_address": printing.address_line(supplier), "salesman": sman,
            "docno": str(master.get("docno") or "").strip(),
            "tdate": str(master.get("tdate") or "").strip(),
            "netamt": money(master.get("netamt")), "taxamt": taxamt,
            "cgst": cgst, "sgst": sgst, "igst": igst, "paid": paid, "balance": balance,
            "company": printing.company_info(self.db), "title": "Purchase Bill",
        }

    def render_pdf(self, slno: int = 0, doc_no: str = "", path: str = "") -> str:
        data = self.gather(slno, doc_no)
        comp = data["company"]
        shop = {"name": comp["name"], "address": comp["address"], "phone": comp["phone"], "gst": comp["gst"]}
        details = [("Doc No", data["docno"]), ("Date", data["tdate"]),
                   ("Supplier", str(data["master"].get("suppname") or data["supplier"].get("name") or "").strip()),
                   ("Address", data["supplier_address"])]
        item_cols = [("sno", "#"), ("name", "Item"), ("qty", "Qty"),
                     ("netwgt", "Net Wt"), ("rate", "Rate"), ("amount", "Amount")]
        items = [{**r, "netwgt": str(r["netwgt"]), "rate": str(r["rate"]),
                  "amount": str(r["amount"])} for r in data["rows"]]
        totals = []
        if data["igst"] > 0:
            totals.append(("IGST", format_money(data["igst"])))
        if data["cgst"] > 0:
            totals.append(("CGST", format_money(data["cgst"])))
            totals.append(("SGST", format_money(data["sgst"])))
        totals.append(("Net Amount", format_money(data["netamt"])))
        totals.append(("Paid", format_money(data["paid"])))
        totals.append(("Balance", format_money(data["balance"])))
        return build_document(path, title=data["title"], shop=shop, details=details,
                              items=items, item_columns=item_cols, totals=totals)
