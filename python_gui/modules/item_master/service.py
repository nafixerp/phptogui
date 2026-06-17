"""Item Master rules — port of ItemMasterController (save/delete/rename).

payloadFromRequest builds a candidate row and filters it to the columns present
in `items`. To avoid clobbering unmanaged columns on edit, the desktop only maps
the form keys actually supplied (the controller's Blade form posts them all);
unmanaged columns are left untouched on edit and take DB defaults on add.

Delete: blocked when reserve='Y' or the item has non-zero transaction weight.
"""

from __future__ import annotations

from decimal import Decimal

from ...core.audit import log_delpart
from ...core.auth import AppSession
from ...core.decimals import to_decimal
from .repo import ItemMasterRepo

# form_key -> (column, kind). kind transforms mirror payloadFromRequest().
#   U=upper+trim T=trim F=decimal I=int  YN/RES/DIS/SHOW/NODISC=boolean variants
_MAP: list[tuple[str, str, str]] = [
    ("code", "code", "U"), ("desc", "name", "U"), ("regional", "regionalname", "T"),
    ("grpcode", "grpcode", "T"), ("subgrpcode", "subgrpcode", "T"), ("itype", "itype", "T"),
    ("wastage", "wastage", "F"), ("mcrate", "mcharge", "F"), ("opcost", "opcost", "F"),
    ("cost", "cost", "F"), ("vaperc", "vaperc", "F"), ("vaperqty", "vaperqty", "F"),
    ("ornament", "ornament", "YN"), ("touch", "touch", "F"),
    ("rollower", "rollower", "F"), ("rolupper", "rolupper", "F"),
    ("rollowerqty", "rollowerqty", "I"), ("rolupperqty", "rolupperqty", "I"),
    ("defqty", "defqty", "I"), ("frcode", "code2", "U"),
    ("stktype", "defstktype", "T"), ("qtype", "defquality", "T"), ("qtype", "qtype", "T"),
    ("smith", "defsmith", "T"), ("footer_e", "footer_e", "T"), ("footer_m", "footer_m", "T"),
    ("stonemarg", "stonemarg", "F"), ("rate", "rate", "F"), ("wsrate", "wsrate", "F"),
    ("smithmc", "smithmc", "F"), ("jewlmc", "jewlmc", "F"), ("shedule", "shedule", "U"),
    ("vatcode", "vatcode", "U"), ("stktouch", "stktouch", "F"), ("dmdplt", "dmdplt", "T"),
    ("jewltouch", "jewltouch", "F"), ("prate", "prate", "F"), ("saccode", "saccode", "U"),
    ("billtype", "billtype", "T"), ("stickerwgt", "stickerwgt", "F"), ("minvap", "minvap", "F"),
    ("stkinnos", "stkinnos", "YN"), ("reserve", "reserve", "RES"), ("disable", "disabled", "DIS"),
    ("dontshowinstkrep", "showinstkrep", "SHOW"), ("taxable", "taxable", "YN"),
    ("taxinternal", "taxinternal", "YN"), ("cessinternal", "cessinternal", "YN"),
    ("printvaamt", "printvaamt", "YN"), ("bccompulsory", "bccompulsory", "YN"),
    ("nodisc", "nodisc", "NODISC"), ("stonemust", "stonemust", "YN"), ("vaoffer", "vaoffer", "YN"),
]
_ADD_ZERO_COLS = ["qty", "weight", "stonewgt", "qtyb", "weightb", "stonewgtb",
                  "opqty", "opweight", "opstonewgt", "opqtyb", "opweightb", "opstonewgtb"]


def _truthy(v) -> bool:
    return v not in (None, "", False, 0, "0", "N", "n")


def _transform(kind: str, value):
    if kind == "U":
        return str(value or "").strip().upper()
    if kind == "T":
        return str(value or "").strip()
    if kind == "F":
        return to_decimal(value) or Decimal("0")
    if kind == "I":
        return int(to_decimal(value) or 0)
    if kind == "YN":
        return "Y" if _truthy(value) else "N"
    if kind == "RES":
        return "Y" if _truthy(value) else " "
    if kind == "DIS":
        return 1 if _truthy(value) else 0
    if kind == "SHOW":            # dontshowinstkrep -> showinstkrep
        return "N" if _truthy(value) else "Y"
    if kind == "NODISC":
        return "N" if _truthy(value) else ""
    return value


class ItemMasterError(Exception):
    pass


class ItemMasterService:
    def __init__(self, repo: ItemMasterRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    def options(self) -> dict:
        return self.repo.options()

    def search(self, term: str = "") -> list[dict]:
        return self.repo.search(term.strip())

    def get(self, code: str) -> dict | None:
        return self.repo.get(code)

    def code_exists(self, code: str) -> bool:
        code = str(code or "").strip().upper()
        return self.repo.exists(code) if code else False

    def build_payload(self, form: dict, for_add: bool) -> dict:
        row: dict = {}
        for fk, col, kind in _MAP:
            if fk in form:
                row[col] = _transform(kind, form[fk])
        payload = self.repo.filter_columns(row)
        if for_add:
            cols = self.repo.columns()
            for zc in _ADD_ZERO_COLS:
                if zc in cols and zc not in payload:
                    payload[zc] = 0
        return payload

    def save(self, form: dict, mode: str, code_locked: bool = False) -> str:
        mode = str(mode or "add").strip().lower()
        if mode not in ("add", "edit"):
            raise ItemMasterError("Invalid mode")
        code = str(form.get("code") or "").strip().upper()
        if code == "":
            raise ItemMasterError("Code is required")
        if len(code) > 10:
            raise ItemMasterError("Code maximum length is 10")
        if str(form.get("desc") or "").strip() == "":
            raise ItemMasterError("Description is required")
        if len(str(form.get("desc"))) > 50:
            raise ItemMasterError("Description maximum length is 50")

        exists = self.repo.exists(code)
        if mode == "add" and exists and code_locked:
            mode = "edit"
        if mode == "add" and exists:
            raise ItemMasterError("This item already exists")
        if mode == "edit" and not exists:
            raise ItemMasterError("This item does not exist")

        payload = self.build_payload(form, mode == "add")
        with self.repo.db.transaction() as tx:
            if mode == "add":
                self.repo.insert(tx, payload)
            else:
                self.repo.update(tx, code, payload)
        log_delpart(self.repo.db, self.session, f"Item({code}) {'Added' if mode == 'add' else 'Updated'}",
                    utype="A" if mode == "add" else "E", ttype="R")
        return "Item added successfully" if mode == "add" else "Item updated successfully"

    def delete(self, code: str) -> str:
        code = str(code or "").strip().upper()
        item = self.repo.get(code)
        if not item:
            raise ItemMasterError("This item does not exist")
        if str(item.get("reserve") or "").strip().upper() == "Y":
            raise ItemMasterError("This item is reserved. You cannot delete it")
        if abs(self.repo.transaction_weight(code)) >= 0.0001:
            raise ItemMasterError("Some entries exist with this item. You cannot delete this item")
        self.repo.delete(code)
        log_delpart(self.repo.db, self.session, f"Item({code}) Deleted", utype="D", ttype="R")
        return "Item deleted successfully"

    def rename(self, old_code: str, new_code: str, merge_existing: bool = False) -> dict:
        old_code = str(old_code or "").strip().upper()
        new_code = str(new_code or "").strip().upper()
        if old_code == "" or new_code == "":
            raise ItemMasterError("Old code and new code are required")
        if len(old_code) > 10 or len(new_code) > 10:
            raise ItemMasterError("Item code maximum length is 10")
        if old_code == new_code:
            raise ItemMasterError("Old code and new code are same")
        result = self.repo.rename(old_code, new_code, merge_existing)
        if result.get("success"):
            log_delpart(self.repo.db, self.session, f"Item Code Renamed {old_code} to {new_code}",
                        utype="E", ttype="R")
        return result
