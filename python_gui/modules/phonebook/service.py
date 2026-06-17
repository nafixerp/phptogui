"""Phone Book business rules — port of PhoneBookController.

Read-only. Maps clients rows to contact entries (type label, preferred contact,
WhatsApp/tel/mail URLs) and computes the summary counts. Summary always runs
over contact_status='all' (matches the controller).
"""

from __future__ import annotations

import re

from .repo import PhoneBookRepo

# (code, label) — matches PhoneBookController::buildPayload types.
TYPES = [
    ("C", "Customers"), ("S", "Suppliers"), ("G", "Goldsmiths"), ("J", "Jewellery"),
    ("R", "Refiners"), ("F", "Staff"), ("D", "Depositors"), ("ALL", "All Parties"),
]
CONTACT_STATUS = ["all", "mobile-only", "missing-mobile", "any-contact"]

_TYPE_LABELS = {
    "C": "Customer", "S": "Supplier", "G": "Goldsmith", "J": "Jewellery",
    "R": "Refiner", "F": "Staff", "D": "Depositor",
}


def type_label(ctype: str) -> str:
    c = (ctype or "").strip().upper()
    return _TYPE_LABELS.get(c, c if c != "" else "Party")


def _digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


class PhoneBookService:
    def __init__(self, repo: PhoneBookRepo):
        self.repo = repo

    def list_contacts(self, ctype: str, search: str = "", contact_status: str = "all") -> list[dict]:
        ctype = (ctype or "C").strip().upper()
        rows = self.repo.load_contacts(ctype, search.strip(), contact_status)
        return [self._map(r) for r in rows]

    def summary(self, ctype: str, search: str = "") -> dict:
        rows = self.repo.load_contacts((ctype or "C").strip().upper(), search.strip(), "all")
        def nonempty(field):
            return sum(1 for r in rows if str(r.get(field) or "").strip() != "")
        return {
            "total": len(rows),
            "with_mobile": nonempty("mobile"),
            "with_phone": nonempty("telephone"),
            "with_email": nonempty("email"),
        }

    def quick_lookup(self, phone: str) -> list[dict]:
        needle = (phone or "").strip()
        rows = self.repo.quick_lookup(needle, _digits(needle))
        out = []
        for r in rows:
            mobile = str(r.get("mobile") or "").strip()
            telephone = str(r.get("telephone") or "").strip()
            ctype = str(r.get("ctype") or "").strip().upper()
            out.append({
                "code": str(r.get("code") or "").strip(),
                "name": str(r.get("name") or "").strip(),
                "type": ctype, "type_label": type_label(ctype),
                "mobile": mobile, "telephone": telephone,
                "contact": mobile or telephone,
                "city": str(r.get("city") or "").strip(),
            })
        return out

    @staticmethod
    def _map(row: dict) -> dict:
        def t(field):
            return str(row.get(field) or "").strip()
        mobile, telephone, email = t("mobile"), t("telephone"), t("email")
        ctype = t("ctype")
        return {
            "code": t("code"), "name": t("name"), "ctype": ctype,
            "type_label": type_label(ctype),
            "addr1": t("addr1"), "addr2": t("addr2"), "addr3": t("addr3"),
            "city": t("city"), "telephone": telephone, "mobile": mobile, "email": email,
            "contact": mobile or telephone,
            "grp": t("grp"), "route": t("route"), "carea": t("carea"),
            "dtbirthday": str(row.get("dtbirthday") or ""),
            "dtengagement": str(row.get("dtengagement") or ""),
            "dtmarriage": str(row.get("dtmarriage") or ""),
            "whatsapp_url": ("https://wa.me/" + _digits(mobile)) if mobile else "",
            "tel_url": ("tel:" + (mobile or telephone)) if (mobile or telephone) else "",
            "mail_url": ("mailto:" + email) if email else "",
        }
