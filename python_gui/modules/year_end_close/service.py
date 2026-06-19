"""Year End Account Close — port of ``YearEndAccountCloseController``.

This is the most destructive operation in the system: it deletes historical
transactions up to a closing date, rolls forward opening balances / opening
stock, and optionally resets opening figures. Every action is gated behind a
boolean *flag* (the UI checkboxes), every table/column reference is guarded
against the live schema, and the whole close runs inside a single transaction
so any failure rolls the entire operation back (mirrors Laravel's
``DB::beginTransaction()/commit()/rollBack()``).

Porting notes
-------------
* ``whereDate('tdate','<=',$date)`` → ``DATE(tdate) <= :date`` (compares the
  date portion on both MySQL and SQLite, matching Laravel's cast).
* ``keepbills`` filters header rows to ``control = 2`` when the table has a
  ``control`` column (so finalised/"kept" bills survive the purge).
* Stock roll-forward replays sales/purchase/order/repair/smith/refinery/
  adjustment movements per item to recompute opening figures — a faithful port
  of the controller's movement engine, guarded so absent tables are no-ops.
"""

from __future__ import annotations

from ...core.auth import AppSession
from ...core.db import Database

# All flag keys the controller understands (readFlags()).
FLAG_KEYS = [
    "chsales", "crsales", "sret", "chpurchase", "crpurchase", "purchaseret", "otheritemtran",
    "order", "orderpend", "reppend", "repr", "smith", "refn", "refnpend", "adjustment",
    "kuricolln", "partnersdeposit", "deldaybookentries", "keepbills", "keeppendbills", "dontsp",
    "initopbalie", "initopbalal", "initopstock", "initpartyopwgt", "initsmithjewlopbal",
    "removeaddr", "deloutstockbarcode",
]

_STOCK_OP_COLUMNS = [
    "opweight", "opweightb", "opqty", "opqtyb",
    "opstonewgt", "opstonewgtb", "opstoneamt", "opstoneamtb", "opdmdwgt",
]


class YearEndCloseError(Exception):
    pass


class YearEndCloseService:
    def __init__(self, database: Database, session: AppSession | None = None):
        self.db = database
        self.session = session
        self._col_cache: dict[str, set[str]] = {}

    # -- schema guards ------------------------------------------------------
    def _has(self, table: str) -> bool:
        return self.db.table_exists(table)

    def _cols(self, table: str) -> set[str]:
        key = table.lower()
        if key not in self._col_cache:
            try:
                self._col_cache[key] = {c.lower() for c in self.db.columns(table)} if self._has(table) else set()
            except Exception:
                self._col_cache[key] = set()
        return self._col_cache[key]

    def _hascol(self, table: str, column: str) -> bool:
        return column.lower() in self._cols(table)

    def _tables_exist(self, tables: list[str]) -> bool:
        return all(self._has(t) for t in tables)

    # -- public API ---------------------------------------------------------
    def normalize_flags(self, flags: dict) -> dict:
        return {k: bool(flags.get(k, False)) for k in FLAG_KEYS}

    def close_accounts(self, close_date: str, flags: dict) -> dict:
        """Run the year-end close for the given date and flag set (atomic)."""
        close_date = str(close_date or "").strip()
        if not close_date:
            raise YearEndCloseError("Invalid closing date.")
        flags = self.normalize_flags(flags)

        summary: dict[str, int] = {}
        with self.db.transaction() as tx:
            if flags["chsales"]:
                summary["cash_sales"] = self._delete_sales_by_status(tx, close_date, True, flags["keepbills"], False)
            if flags["crsales"]:
                summary["credit_sales"] = self._delete_sales_by_status(tx, close_date, False, flags["keepbills"], flags["keeppendbills"])
            if flags["sret"]:
                summary["sales_return"] = self._delete_simple(tx, "salesrm", "salesrd", close_date, flags["keepbills"], "sr = 'R'")
            if flags["chpurchase"]:
                summary["cash_purchase"] = self._delete_purchase_by_status(tx, close_date, True, flags["keepbills"])
            if flags["crpurchase"]:
                summary["credit_purchase"] = self._delete_purchase_by_status(tx, close_date, False, flags["keepbills"])
            if flags["purchaseret"]:
                summary["purchase_return"] = self._delete_simple(tx, "purchaserm", "purchaserd", close_date, flags["keepbills"], "pr = 'R'")
            if flags["otheritemtran"]:
                summary["other_item"] = self._delete_other_items(tx, close_date)
            if flags["orderpend"]:
                summary["pending_order"] = self._delete_order_by_status(tx, close_date, True, flags["keepbills"])
            if flags["order"]:
                summary["closed_order"] = self._delete_order_by_status(tx, close_date, False, flags["keepbills"])
            if flags["reppend"]:
                summary["pending_repair"] = self._delete_simple(tx, "repairm", "repaird", close_date, flags["keepbills"], "status = 1")
            if flags["repr"]:
                summary["repair"] = self._delete_simple(tx, "repairm", "repaird", close_date, flags["keepbills"], "status <> 1")
            if flags["smith"]:
                summary["smith"] = self._delete_simple(tx, "smithm", "smithd", close_date, flags["keepbills"], None)
            if flags["refnpend"]:
                summary["pending_refinery"] = self._delete_simple(tx, "refinerym", "refineryd", close_date, flags["keepbills"], "status = 1")
            if flags["refn"]:
                summary["refinery"] = self._delete_simple(tx, "refinerym", "refineryd", close_date, flags["keepbills"], "status <> 1")
            if flags["adjustment"]:
                summary["adjustment"] = self._delete_by_date_control(tx, "itemadj", "tdate", close_date, flags["keepbills"])
            if flags["partnersdeposit"]:
                summary["partners_deposit"] = self._delete_by_date_control(tx, "wgtrcptpmnt", "tdate", close_date, flags["keepbills"])
            if flags["kuricolln"]:
                summary["kuri"] = self._delete_by_date_control(tx, "kuricolln", "tdate", close_date, flags["keepbills"])

            # When kuri is NOT being deleted, mark <= date collections closed.
            if not flags["kuricolln"] and self._hascol("kuricolln", "closed"):
                tx.execute("UPDATE kuricolln SET closed = 'Y' WHERE DATE(tdate) <= :d", {"d": close_date})

            if flags["deldaybookentries"]:
                summary["daybook"] = self._roll_forward_daybook(tx, close_date, flags["keepbills"], flags["dontsp"])

            if flags["otheritemtran"]:
                self._roll_forward_other_items(tx, close_date)

            if not flags["initopstock"]:
                self._roll_forward_stock(tx, close_date, flags)

            if flags["initopbalie"]:
                self._reset_account_type_balances(tx, ["R", "E"])

            if flags["initopbalal"]:
                self._reset_account_type_balances(tx, ["A", "L"])
                if self._has("clients"):
                    self._update_all(tx, "clients", {"opbalance": 0, "opbalanceb": 0})

            if flags["initopstock"]:
                self._reset_opening_stock(tx)

            if flags["initpartyopwgt"] and self._has("clientsgs"):
                self._update_all(tx, "clientsgs", {"opweight": 0, "opweightb": 0})

            if flags["initsmithjewlopbal"]:
                if self._has("clientsgs"):
                    self._update_all(tx, "clientsgs", {"opweight": 0, "opweightb": 0})
                if self._hascol("clients", "ctype"):
                    self._update_filtered(tx, "clients", {"opbalance": 0, "opbalanceb": 0}, "ctype", ["J", "G"])
                if self._hascol("accountm", "actype2"):
                    self._update_filtered(tx, "accountm", {"opbal": 0, "opbalb": 0}, "actype2", ["J", "G"])

            if flags["removeaddr"] and self._has("clients"):
                self._update_all(tx, "clients", {
                    "addr1": "", "addr2": "", "addr3": "", "city": "", "telephone": "", "mobile": "",
                })

            if not flags["orderpend"] and self._hascol("orderm", "closed"):
                tx.execute("UPDATE orderm SET closed = 1 WHERE DATE(tdate) <= :d", {"d": close_date})

            if flags["deloutstockbarcode"]:
                summary["barcode"] = self._delete_outstock_barcodes(tx)

        return {"close_date": close_date, "summary": summary,
                "control": 2 if flags["keepbills"] else 1}

    # -- delete helpers -----------------------------------------------------
    def _pluck_slnos(self, tx, sql: str, params: dict) -> list:
        rows = tx.fetchall(sql, params)
        out = []
        for r in rows:
            v = r.get("slno")
            if v is None:
                continue
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                out.append(v)
        return out

    def _delete_in(self, tx, table: str, column: str, values: list) -> int:
        if not values or not self._has(table) or not self._hascol(table, column):
            return 0
        ph = ", ".join(f":v{i}" for i in range(len(values)))
        params = {f"v{i}": v for i, v in enumerate(values)}
        res = tx.execute(f"DELETE FROM {table} WHERE {column} IN ({ph})", params)
        return int(getattr(res, "rowcount", 0) or 0)

    def _delete_sales_by_status(self, tx, date: str, cash: bool, keep_bills: bool, keep_pending: bool) -> int:
        if not self._has("salesm"):
            return 0
        where = ["DATE(tdate) <= :d"]
        params = {"d": date}
        where.append("status = 3" if cash else "status <> 3")
        if keep_bills and self._hascol("salesm", "control"):
            where.append("control = 2")
        if keep_pending and self._hascol("salesm", "opbill"):
            where.append("opbill <> 1")
        slnos = self._pluck_slnos(tx, f"SELECT slno FROM salesm WHERE {' AND '.join(where)}", params)
        if not slnos:
            return 0
        for tbl in ("salesd", "salesrd", "salesrm", "purchased", "purchasem"):
            self._delete_in(tx, tbl, "slno", slnos)
        self._delete_in(tx, "collection", "slno", slnos)
        return self._delete_in(tx, "salesm", "slno", slnos)

    def _delete_purchase_by_status(self, tx, date: str, cash: bool, keep_bills: bool) -> int:
        if not self._has("purchasem"):
            return 0
        where = ["DATE(tdate) <= :d", "pr <> 'E'"]
        params = {"d": date}
        where.append("status = 3" if cash else "status <> 3")
        if keep_bills and self._hascol("purchasem", "control"):
            where.append("control = 2")
        slnos = self._pluck_slnos(tx, f"SELECT slno FROM purchasem WHERE {' AND '.join(where)}", params)
        if not slnos:
            return 0
        for tbl in ("purchased", "purchaserd", "purchaserm"):
            self._delete_in(tx, tbl, "slno", slnos)
        return self._delete_in(tx, "purchasem", "slno", slnos)

    def _delete_order_by_status(self, tx, date: str, pending: bool, keep_bills: bool) -> int:
        if not self._has("orderm"):
            return 0
        where = ["DATE(tdate) <= :d"]
        params = {"d": date}
        where.append("status = 1" if pending else "status <> 1")
        if keep_bills and self._hascol("orderm", "control"):
            where.append("control = 2")
        rows = tx.fetchall(f"SELECT slno, ordno FROM orderm WHERE {' AND '.join(where)}", params)
        if not rows:
            return 0
        slnos = [int(r["slno"]) for r in rows if r.get("slno") is not None]
        ordnos = [str(r["ordno"]).strip() for r in rows if r.get("ordno") not in (None, "")]
        for tbl in ("orderd", "orderdga", "salesrd", "salesrm", "purchased", "purchasem"):
            self._delete_in(tx, tbl, "slno", slnos)
        if ordnos:
            self._delete_in(tx, "advafter", "ordno", ordnos)
        return self._delete_in(tx, "orderm", "slno", slnos)

    def _delete_simple(self, tx, header: str, detail: str, date: str, keep_bills: bool, raw_cond: str | None) -> int:
        if not self._has(header):
            return 0
        where = ["DATE(tdate) <= :d"]
        params = {"d": date}
        if raw_cond:
            where.append(raw_cond)
        if keep_bills and self._hascol(header, "control"):
            where.append("control = 2")
        slnos = self._pluck_slnos(tx, f"SELECT slno FROM {header} WHERE {' AND '.join(where)}", params)
        if not slnos:
            return 0
        self._delete_in(tx, detail, "slno", slnos)
        return self._delete_in(tx, header, "slno", slnos)

    def _delete_other_items(self, tx, date: str) -> int:
        deleted = 0
        if self._tables_exist(["oitemtrand", "oitemtranm"]):
            ids = [r["slno"] for r in tx.fetchall("SELECT slno FROM oitemtranm WHERE DATE(tdate) <= :d", {"d": date})
                   if r.get("slno") is not None]
            deleted += self._delete_in(tx, "oitemtrand", "slno", ids)
        if self._has("oitemtranm"):
            res = tx.execute("DELETE FROM oitemtranm WHERE DATE(tdate) <= :d", {"d": date})
            deleted += int(getattr(res, "rowcount", 0) or 0)
        return deleted

    def _delete_by_date_control(self, tx, table: str, date_col: str, date: str, keep_bills: bool) -> int:
        if not self._has(table):
            return 0
        where = [f"DATE({date_col}) <= :d"]
        if keep_bills and self._hascol(table, "control"):
            where.append("control = 2")
        res = tx.execute(f"DELETE FROM {table} WHERE {' AND '.join(where)}", {"d": date})
        return int(getattr(res, "rowcount", 0) or 0)

    # -- roll-forward: daybook ---------------------------------------------
    def _roll_forward_daybook(self, tx, date: str, keep_bills: bool, dont_sp: bool) -> int:
        if not self._tables_exist(["accountm", "daybook"]):
            return 0
        has_control = self._hascol("daybook", "control")
        accounts = tx.fetchall("SELECT accode, opbal, opbalb FROM accountm")
        for row in accounts:
            accode = row.get("accode")
            opbal = float(row.get("opbal") or 0)
            opbalb = float(row.get("opbalb") or 0)
            if has_control:
                s1 = tx.scalar("SELECT COALESCE(SUM(amount),0) FROM daybook WHERE accode = :a AND DATE(tdate) <= :d AND control = 1",
                               {"a": accode, "d": date}) or 0
                s2 = tx.scalar("SELECT COALESCE(SUM(amount),0) FROM daybook WHERE accode = :a AND DATE(tdate) <= :d AND control = 2",
                               {"a": accode, "d": date}) or 0
            else:
                s1 = 0
                s2 = tx.scalar("SELECT COALESCE(SUM(amount),0) FROM daybook WHERE accode = :a AND DATE(tdate) <= :d",
                               {"a": accode, "d": date}) or 0
            tx.execute("UPDATE accountm SET opbal = :ob, opbalb = :obb WHERE accode = :a",
                       {"ob": opbal + float(s1), "obb": opbalb + float(s2), "a": accode})

        if self._has("clients"):
            tx.execute("UPDATE clients SET opbalance = COALESCE("
                       "(SELECT accountm.opbal FROM accountm WHERE accountm.accode = clients.code), opbalance)")
            tx.execute("UPDATE clients SET opbalanceb = COALESCE("
                       "(SELECT accountm.opbalb FROM accountm WHERE accountm.accode = clients.code), opbalanceb)")

        where = ["DATE(tdate) <= :d"]
        params = {"d": date}
        if keep_bills and has_control:
            where.append("control = 2")
        if dont_sp and self._hascol("accountm", "sp"):
            where.append("slno NOT IN (SELECT db.slno FROM daybook db "
                         "JOIN accountm ON accountm.accode = db.accode WHERE accountm.sp = 1)")
        slnos = self._pluck_slnos(tx, f"SELECT slno FROM daybook WHERE {' AND '.join(where)}", params)
        if not slnos:
            return 0
        self._delete_in(tx, "daybookpart", "slno", slnos)
        self._delete_in(tx, "daybookratewgt", "slno", slnos)
        return self._delete_in(tx, "daybook", "slno", slnos)

    def _roll_forward_other_items(self, tx, date: str) -> None:
        if not self._tables_exist(["itemsothers", "oitemtranm", "oitemtrand"]):
            return
        for row in tx.fetchall("SELECT code, opstock FROM itemsothers"):
            code = row.get("code")
            sold = tx.scalar(
                "SELECT COALESCE(SUM(d.qty),0) FROM oitemtrand d JOIN oitemtranm m ON m.slno = d.slno "
                "WHERE d.code = :c AND m.tr = 'S' AND DATE(m.tdate) <= :d", {"c": code, "d": date}) or 0
            purchased = tx.scalar(
                "SELECT COALESCE(SUM(d.qty),0) FROM oitemtrand d JOIN oitemtranm m ON m.slno = d.slno "
                "WHERE d.code = :c AND m.tr = 'P' AND DATE(m.tdate) <= :d", {"c": code, "d": date}) or 0
            tx.execute("UPDATE itemsothers SET opstock = :v WHERE code = :c",
                       {"v": float(row.get("opstock") or 0) - float(sold) + float(purchased), "c": code})

    # -- resets -------------------------------------------------------------
    def _update_all(self, tx, table: str, values: dict) -> None:
        cols = {k: v for k, v in values.items() if self._hascol(table, k)}
        if not cols:
            return
        sets = ", ".join(f"{k} = :{k}" for k in cols)
        tx.execute(f"UPDATE {table} SET {sets}", dict(cols))

    def _update_filtered(self, tx, table: str, values: dict, col: str, in_values: list) -> None:
        cols = {k: v for k, v in values.items() if self._hascol(table, k)}
        if not cols or not self._hascol(table, col):
            return
        ph = ", ".join(f":f{i}" for i in range(len(in_values)))
        params = {**cols, **{f"f{i}": v for i, v in enumerate(in_values)}}
        sets = ", ".join(f"{k} = :{k}" for k in cols)
        tx.execute(f"UPDATE {table} SET {sets} WHERE {col} IN ({ph})", params)

    def _reset_account_type_balances(self, tx, types: list) -> None:
        if self._hascol("accountm", "actype1"):
            self._update_filtered(tx, "accountm", {"opbal": 0, "opbalb": 0}, "actype1", types)

    def _reset_opening_stock(self, tx) -> None:
        for table in ("items", "itemsstk"):
            if self._has(table):
                self._update_all(tx, table, {c: 0 for c in _STOCK_OP_COLUMNS})

    def _delete_outstock_barcodes(self, tx) -> int:
        if not self._has("barcode"):
            return 0
        where = ["stk = 'N'"]
        if self._has("modelm"):
            where.append("bcode NOT IN (SELECT bcode FROM modelm WHERE ir = 'I' AND pend = 'Y')")
        bcodes = [r["bcode"] for r in tx.fetchall(f"SELECT bcode FROM barcode WHERE {' AND '.join(where)}")
                  if r.get("bcode") is not None]
        if not bcodes:
            return 0
        self._delete_in(tx, "barcodedmd", "bcode", bcodes)
        return self._delete_in(tx, "barcode", "bcode", bcodes)

    # -- roll-forward: stock (movement engine) ------------------------------
    def _software_flag(self, tx, code: str, default: str = "N") -> bool:
        if not self._has("generals"):
            return default.strip().upper() == "Y"
        val = tx.scalar("SELECT cvalue FROM generals WHERE code = :c", {"c": code})
        val = (str(val).strip() if val is not None else default)
        return val.upper() == "Y"

    def _roll_forward_stock(self, tx, date: str, flags: dict) -> None:
        same_stock = self._software_flag(tx, "SameStock", "N")
        strict = self._software_flag(tx, "StktypeStrict", "N")
        if strict and self._hascol("itemsstk", "stktype"):
            self._roll_forward_typed(tx, date, flags, same_stock)
            return
        self._roll_forward_level(tx, date, flags, 2, same_stock, True)
        if not same_stock:
            self._roll_forward_level(tx, date, flags, 1, False, False)

    def _roll_forward_typed(self, tx, date: str, flags: dict, same_stock: bool) -> None:
        if not self._has("itemsstk"):
            return
        rows = tx.fetchall(
            "SELECT s.code AS code, s.stktype AS stktype, "
            "COALESCE(s.opqtyb,0) AS opqtyb, COALESCE(s.opweightb,0) AS opweightb, "
            "COALESCE(s.opstonewgtb,0) AS opstonewgtb, COALESCE(s.opstoneamtb,0) AS opstoneamtb, "
            "COALESCE(i.stonemarg,0) AS stonemarg "
            "FROM itemsstk s LEFT JOIN items i ON i.code = s.code ORDER BY s.code, s.stktype")
        for row in rows:
            state = {"qty": float(row["opqtyb"]), "weight": float(row["opweightb"]),
                     "stonewgt": float(row["opstonewgtb"]), "stoneamt": float(row["opstoneamtb"]), "dmdwgt": 0.0}
            self._apply_stock_flags(tx, state, str(row["code"]).strip(), date, flags, 2,
                                    str(row["stktype"]), float(row["stonemarg"]), False)
            upd = {"opqtyb": state["qty"], "opweightb": state["weight"], "opstonewgtb": state["stonewgt"]}
            if self._hascol("itemsstk", "opstoneamtb"):
                upd["opstoneamtb"] = state["stoneamt"]
            if same_stock:
                for src, dst in [("qty", "opqty"), ("weight", "opweight"), ("stonewgt", "opstonewgt"), ("stoneamt", "opstoneamt")]:
                    if self._hascol("itemsstk", dst):
                        upd[dst] = state[src]
            sets = ", ".join(f"{k} = :{k}" for k in upd)
            tx.execute(f"UPDATE itemsstk SET {sets} WHERE code = :c AND stktype = :st",
                       {**upd, "c": row["code"], "st": row["stktype"]})

        if not self._has("items"):
            return
        codes = [r["code"] for r in tx.fetchall("SELECT DISTINCT code FROM itemsstk")]
        for code in codes:
            agg = tx.fetchall(
                "SELECT COALESCE(SUM(opqtyb),0) AS q, COALESCE(SUM(opweightb),0) AS w, "
                "COALESCE(SUM(opstonewgtb),0) AS sw, COALESCE(SUM(opstoneamtb),0) AS sa "
                "FROM itemsstk WHERE code = :c", {"c": code})[0]
            upd = {"opqtyb": float(agg["q"]), "opweightb": float(agg["w"]), "opstonewgtb": float(agg["sw"])}
            if self._hascol("itemsstk", "opstoneamtb") and self._hascol("items", "opstoneamtb"):
                upd["opstoneamtb"] = float(agg["sa"])
            if same_stock:
                for src, dst in [("opqtyb", "opqty"), ("opweightb", "opweight"), ("opstonewgtb", "opstonewgt")]:
                    if self._hascol("items", dst):
                        upd[dst] = upd[src]
                if "opstoneamtb" in upd and self._hascol("items", "opstoneamt"):
                    upd["opstoneamt"] = upd["opstoneamtb"]
            sets = ", ".join(f"{k} = :{k}" for k in upd)
            tx.execute(f"UPDATE items SET {sets} WHERE code = :c", {**upd, "c": code})

    def _roll_forward_level(self, tx, date: str, flags: dict, control_mode: int, same_stock: bool, include_dmd: bool) -> None:
        if not self._has("items"):
            return
        suffix = "" if control_mode == 1 else "b"
        qty_c, wgt_c = f"opqty{suffix}", f"opweight{suffix}"
        swgt_c, samt_c = f"opstonewgt{suffix}", f"opstoneamt{suffix}"
        samt_sel = f"COALESCE({samt_c},0)" if self._hascol("items", samt_c) else "0"
        dmd_sel = "COALESCE(opdmdwgt,0)" if (include_dmd and self._hascol("items", "opdmdwgt")) else "0"
        rows = tx.fetchall(
            f"SELECT code, COALESCE({qty_c},0) AS q, COALESCE({wgt_c},0) AS w, "
            f"COALESCE({swgt_c},0) AS sw, COALESCE(stonemarg,0) AS sm, "
            f"{samt_sel} AS sa, {dmd_sel} AS dw FROM items ORDER BY code")
        for row in rows:
            state = {"qty": float(row["q"]), "weight": float(row["w"]), "stonewgt": float(row["sw"]),
                     "stoneamt": float(row["sa"]), "dmdwgt": float(row["dw"])}
            self._apply_stock_flags(tx, state, str(row["code"]).strip(), date, flags, control_mode,
                                    None, float(row["sm"]), include_dmd)
            upd = {qty_c: state["qty"], wgt_c: state["weight"], swgt_c: state["stonewgt"]}
            if self._hascol("items", samt_c):
                upd[samt_c] = state["stoneamt"]
            if include_dmd and self._hascol("items", "opdmdwgt"):
                upd["opdmdwgt"] = state["dmdwgt"]
            if same_stock and control_mode == 2:
                for src, dst in [("qty", "opqty"), ("weight", "opweight"), ("stonewgt", "opstonewgt"), ("stoneamt", "opstoneamt")]:
                    if self._hascol("items", dst):
                        upd[dst] = state[src]
            sets = ", ".join(f"{k} = :{k}" for k in upd)
            tx.execute(f"UPDATE items SET {sets} WHERE code = :c", {**upd, "c": row["code"]})

    def _apply_stock_flags(self, tx, state: dict, code: str, date: str, flags: dict,
                           control_mode: int, stock_type: str | None, stone_marg: float, include_dmd: bool) -> None:
        if flags["chsales"]:
            self._apply(state, self._mv_sales(tx, code, date, True, control_mode, stock_type, stone_marg, include_dmd))
        if flags["crsales"]:
            self._apply(state, self._mv_sales(tx, code, date, False, control_mode, stock_type, stone_marg, include_dmd))
        if flags["sret"]:
            self._apply(state, self._mv_sales_return(tx, code, date, control_mode, stock_type, stone_marg, include_dmd))
        if flags["chpurchase"]:
            self._apply(state, self._mv_purchase(tx, code, date, True, control_mode, stock_type, include_dmd))
        if flags["crpurchase"]:
            self._apply(state, self._mv_purchase(tx, code, date, False, control_mode, stock_type, include_dmd))
        if flags["purchaseret"]:
            self._apply(state, self._mv_purchase_return(tx, code, date, control_mode, stock_type))
        if flags["orderpend"]:
            self._apply(state, self._mv_order(tx, code, date, True, control_mode, stock_type))
        if flags["order"]:
            self._apply(state, self._mv_order(tx, code, date, False, control_mode, stock_type))
        if flags["repr"]:
            self._apply(state, self._mv_repair(tx, code, date, False, control_mode, stock_type))
        if flags["reppend"]:
            self._apply(state, self._mv_repair(tx, code, date, True, control_mode, stock_type))
        if flags["smith"]:
            self._apply(state, self._mv_smith(tx, code, date, control_mode, stock_type))
        if flags["refn"]:
            self._apply(state, self._mv_refinery(tx, code, date, False, control_mode, stock_type))
        if flags["refnpend"]:
            self._apply(state, self._mv_refinery(tx, code, date, True, control_mode, stock_type))
        if flags["adjustment"]:
            self._apply(state, self._mv_item_adjustment(tx, code, date, control_mode, stock_type))

    # -- movement primitives ------------------------------------------------
    @staticmethod
    def _zero() -> dict:
        return {"qty": 0.0, "weight": 0.0, "stonewgt": 0.0, "stoneamt": 0.0, "dmdwgt": 0.0}

    @staticmethod
    def _apply(state: dict, mv: dict) -> None:
        for k in ("qty", "weight", "stonewgt", "stoneamt", "dmdwgt"):
            state[k] = float(state.get(k) or 0) + float(mv.get(k) or 0)

    @staticmethod
    def _signed(row: dict, qs: int, ws: int, sws: int, sas: int, ds: int, stone_marg: float) -> dict:
        stoneamt = float(row.get("stoneamt") or 0)
        if stone_marg != 0.0 and stoneamt != 0.0:
            stoneamt -= (stoneamt * stone_marg) / 100
        return {"qty": float(row.get("qty") or 0) * qs, "weight": float(row.get("weight") or 0) * ws,
                "stonewgt": float(row.get("stonewgt") or 0) * sws, "stoneamt": stoneamt * sas,
                "dmdwgt": float(row.get("dmdwgt") or 0) * ds}

    def _control_cond(self, table: str, alias: str, control_mode: int) -> str:
        if not self._hascol(table, "control"):
            return "1=1"
        pref = f"{alias}." if alias else ""
        return f"{pref}control = 1" if control_mode == 1 else f"{pref}control <= 2"

    def _col_expr(self, table: str, column: str, alias: str = "") -> str:
        if not self._hascol(table, column):
            return "0"
        return (f"{alias}." if alias else "") + column

    def _stock_filter(self, table: str, alias: str, stock_type: str | None, params: dict) -> str:
        if not stock_type or not str(stock_type).strip() or not self._hascol(table, "stktype"):
            return ""
        key = f"st_{len(params)}"
        params[key] = stock_type
        return f" AND {alias}.stktype = :{key}"

    def _stock_where(self, table: str, column: str, stock_type: str | None, params: dict) -> str:
        if not stock_type or not str(stock_type).strip() or not self._hascol(table, column):
            return ""
        key = f"st_{len(params)}"
        params[key] = stock_type
        return f" AND {column} = :{key}"

    def _sum_row(self, tx, sql: str, params: dict) -> dict:
        rows = tx.fetchall(sql, params)
        return rows[0] if rows else self._zero()

    def _mv_sales(self, tx, code, date, cash, control_mode, stock_type, stone_marg, include_dmd) -> dict:
        mv = self._zero()
        status_op = "= 3" if cash else "<> 3"
        jcode = " AND (TRIM(COALESCE(sd.jcode, '')) = '')" if self._hascol("salesd", "jcode") else ""
        if self._tables_exist(["salesd", "salesm"]):
            p = {"c": code, "d": date}
            sf = self._stock_filter("salesd", "sd", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(sd.qty,0)) qty, SUM(COALESCE(sd.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('salesd','stonewgt','sd')},0)) stonewgt,
                    SUM(COALESCE({self._col_expr('salesd','stoneprice','sd')},0)) stoneamt,
                    SUM(COALESCE({self._col_expr('salesd','dmdwgt','sd')},0)) dmdwgt
                FROM salesd sd JOIN salesm sm ON sm.slno = sd.slno
                WHERE sd.code = :c AND sm.status {status_op} AND DATE(sm.tdate) <= :d{jcode}
                    AND {self._control_cond('salesm','sm',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, -1, -1, -1, -1, -1, stone_marg))
        if self._tables_exist(["salesrd", "salesm"]):
            p = {"c": code, "d": date}
            sf = self._stock_filter("salesrd", "srd", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(srd.qty,0)) qty, SUM(COALESCE(srd.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('salesrd','stonewgt','srd')},0)) stonewgt,
                    SUM(COALESCE({self._col_expr('salesrd','stoneprice','srd')},0)) stoneamt,
                    SUM(COALESCE({self._col_expr('salesrd','dmdwgt','srd')},0)) dmdwgt
                FROM salesrd srd JOIN salesm sm ON sm.slno = srd.slno
                WHERE srd.code = :c AND sm.status {status_op} AND DATE(sm.tdate) <= :d
                    AND {self._control_cond('salesm','sm',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, 1, 1, 1, 1, 1, stone_marg))
        if self._tables_exist(["purchased", "salesm"]):
            p = {"c": code, "d": date}
            sf = self._stock_filter("purchased", "pd", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(pd.qty,0)) qty, SUM(COALESCE(pd.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('purchased','stwgt','pd')},0)) stonewgt,
                    SUM(COALESCE({self._col_expr('purchased','stprice','pd')},0)) stoneamt, 0 dmdwgt
                FROM purchased pd JOIN salesm sm ON sm.slno = pd.slno
                WHERE pd.code = :c AND sm.status {status_op} AND DATE(sm.tdate) <= :d
                    AND {self._control_cond('salesm','sm',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, 1, 1, 1, 1, 0, 0))
        if include_dmd and self._tables_exist(["purchased_dmddet", "purchasem", "salesm"]) and self._hascol("purchased_dmddet", "carats"):
            carats = tx.scalar(f"""
                SELECT SUM(COALESCE(pdd.carats,0)) FROM purchased_dmddet pdd
                JOIN purchasem pm ON pm.slno = pdd.slno JOIN salesm sm ON sm.slno = pm.slno
                WHERE pdd.code = :c AND sm.status {status_op} AND DATE(sm.tdate) <= :d
                    AND {self._control_cond('salesm','sm',control_mode)}""", {"c": code, "d": date}) or 0
            mv["dmdwgt"] += float(carats)
        return mv

    def _mv_sales_return(self, tx, code, date, control_mode, stock_type, stone_marg, include_dmd) -> dict:
        if not self._tables_exist(["salesrd", "salesrm"]):
            return self._zero()
        p = {"c": code, "d": date}
        sf = self._stock_filter("salesrd", "srd", stock_type, p)
        row = self._sum_row(tx, f"""
            SELECT SUM(COALESCE(srd.qty,0)) qty, SUM(COALESCE(srd.weight,0)) weight,
                SUM(COALESCE({self._col_expr('salesrd','stonewgt','srd')},0)) stonewgt,
                SUM(COALESCE({self._col_expr('salesrd','stoneprice','srd')},0)) stoneamt,
                SUM(COALESCE({self._col_expr('salesrd','dmdwgt','srd')},0)) dmdwgt
            FROM salesrd srd JOIN salesrm srm ON srm.slno = srd.slno
            WHERE srd.code = :c AND DATE(srm.tdate) <= :d AND srm.sr = 'R'
                AND {self._control_cond('salesrm','srm',control_mode)}{sf}""", p)
        return self._signed(row, 1, 1, 1, 1, 1 if include_dmd else 0, stone_marg)

    def _mv_purchase(self, tx, code, date, cash, control_mode, stock_type, include_dmd) -> dict:
        if not self._has("purchasem"):
            return self._zero()
        mv = self._zero()
        status_op = "= 3" if cash else "<> 3"
        if self._tables_exist(["purchased", "purchasem"]):
            p = {"c": code, "d": date}
            sf = self._stock_filter("purchased", "pd", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(pd.qty,0)) qty, SUM(COALESCE(pd.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('purchased','stwgt','pd')},0)) stonewgt,
                    SUM(COALESCE({self._col_expr('purchased','stprice','pd')},0)) stoneamt, 0 dmdwgt
                FROM purchased pd JOIN purchasem pm ON pm.slno = pd.slno
                WHERE pd.code = :c AND pm.status {status_op} AND DATE(pm.tdate) <= :d AND pm.pr <> 'E'
                    AND {self._control_cond('purchasem','pm',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, 1, 1, 1, 1, 0, 0))
        if self._tables_exist(["purchaserd", "purchasem"]):
            p = {"c": code, "d": date}
            sf = self._stock_filter("purchaserd", "prd", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(prd.qty,0)) qty, SUM(COALESCE(prd.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('purchaserd','stwgt','prd')},0)) stonewgt,
                    SUM(COALESCE({self._col_expr('purchaserd','stprice','prd')},0)) stoneamt, 0 dmdwgt
                FROM purchaserd prd JOIN purchasem pm ON pm.slno = prd.slno
                WHERE prd.code = :c AND pm.status {status_op} AND DATE(pm.tdate) <= :d AND pm.pr <> 'E'
                    AND {self._control_cond('purchasem','pm',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, -1, -1, -1, -1, 0, 0))
        if include_dmd and self._tables_exist(["purchased_dmddet", "purchasem"]) and self._hascol("purchased_dmddet", "carats"):
            carats = tx.scalar(f"""
                SELECT SUM(COALESCE(pdd.carats,0)) FROM purchased_dmddet pdd
                JOIN purchasem pm ON pm.slno = pdd.slno
                WHERE pdd.code = :c AND pm.status {status_op} AND DATE(pm.tdate) <= :d AND pm.pr <> 'E'
                    AND {self._control_cond('purchasem','pm',control_mode)}""", {"c": code, "d": date}) or 0
            mv["dmdwgt"] += float(carats)
        return mv

    def _mv_purchase_return(self, tx, code, date, control_mode, stock_type) -> dict:
        if not self._tables_exist(["purchaserd", "purchaserm"]):
            return self._zero()
        p = {"c": code, "d": date}
        sf = self._stock_filter("purchaserd", "prd", stock_type, p)
        row = self._sum_row(tx, f"""
            SELECT SUM(COALESCE(prd.qty,0)) qty, SUM(COALESCE(prd.weight,0)) weight,
                SUM(COALESCE({self._col_expr('purchaserd','stwgt','prd')},0)) stonewgt,
                SUM(COALESCE({self._col_expr('purchaserd','stprice','prd')},0)) stoneamt, 0 dmdwgt
            FROM purchaserd prd JOIN purchaserm prm ON prm.slno = prd.slno
            WHERE prd.code = :c AND DATE(prm.tdate) <= :d AND prm.pr = 'R'
                AND {self._control_cond('purchaserm','prm',control_mode)}{sf}""", p)
        return self._signed(row, -1, -1, -1, -1, 0, 0)

    def _mv_order(self, tx, code, date, pending, control_mode, stock_type) -> dict:
        if not self._has("orderm"):
            return self._zero()
        mv = self._zero()
        status_op = "= 1" if pending else "<> 1"
        if self._tables_exist(["purchased", "orderm"]):
            p = {"c": code, "d": date}
            sf = self._stock_filter("purchased", "pd", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(pd.qty,0)) qty, SUM(COALESCE(pd.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('purchased','stwgt','pd')},0)) stonewgt,
                    SUM(COALESCE({self._col_expr('purchased','stprice','pd')},0)) stoneamt, 0 dmdwgt
                FROM purchased pd JOIN orderm om ON om.slno = pd.slno
                WHERE pd.code = :c AND om.status {status_op} AND DATE(om.tdate) <= :d
                    AND {self._control_cond('orderm','om',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, 1, 1, 1, 1, 0, 0))
        if self._tables_exist(["orderdga", "orderm"]):
            p = {"c": code, "d": date}
            sf = self._stock_filter("orderdga", "odg", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(odg.qty,0)) qty, SUM(COALESCE(odg.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('orderdga','stonewgt','odg')},0)) stonewgt, 0 stoneamt, 0 dmdwgt
                FROM orderdga odg JOIN orderm om ON om.slno = odg.slno
                WHERE odg.code = :c AND om.status {status_op} AND DATE(om.tdate) <= :d
                    AND {self._control_cond('orderm','om',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, 1, 1, 1, 0, 0, 0))
        if self._tables_exist(["orderdga", "orderm", "advafter"]):
            p = {"c": code, "d": date}
            sf = self._stock_filter("orderdga", "odg", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(odg.qty,0)) qty, SUM(COALESCE(odg.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('orderdga','stonewgt','odg')},0)) stonewgt, 0 stoneamt, 0 dmdwgt
                FROM orderdga odg JOIN advafter aa ON aa.slno = odg.slno JOIN orderm om ON om.ordno = aa.ordno
                WHERE odg.code = :c AND om.status {status_op} AND DATE(aa.tdate) <= :d
                    AND {self._control_cond('advafter','aa',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, 1, 1, 1, 0, 0, 0))
        if self._tables_exist(["salesrd", "orderm"]):
            p = {"c": code, "d": date}
            sf = self._stock_filter("salesrd", "srd", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(srd.qty,0)) qty, SUM(COALESCE(srd.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('salesrd','stonewgt','srd')},0)) stonewgt,
                    SUM(COALESCE({self._col_expr('salesrd','stoneprice','srd')},0)) stoneamt, 0 dmdwgt
                FROM salesrd srd JOIN orderm om ON om.slno = srd.slno
                WHERE srd.code = :c AND om.status {status_op} AND DATE(om.tdate) <= :d
                    AND {self._control_cond('orderm','om',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, 1, 1, 1, 1, 0, 0))
        return mv

    def _mv_repair(self, tx, code, date, pending, control_mode, stock_type) -> dict:
        if not self._tables_exist(["repaird", "repairm"]):
            return self._zero()
        mv = self._zero()
        status_op = "= 1" if pending else "<> 1"
        for givrec, sign in (("R", 1), ("G", -1)):
            p = {"c": code, "g": givrec, "d": date}
            sf = self._stock_filter("repaird", "rd", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(rd.qty,0)) qty, SUM(COALESCE(rd.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('repaird','stonewgt','rd')},0)) stonewgt,
                    SUM(COALESCE({self._col_expr('repaird','stoneprice','rd')},0)) stoneamt, 0 dmdwgt
                FROM repaird rd JOIN repairm rm ON rm.slno = rd.slno
                WHERE rd.code = :c AND rd.givrec = :g AND rm.status {status_op} AND DATE(rm.tdate) <= :d
                    AND {self._control_cond('repairm','rm',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, sign, sign, sign, sign, 0, 0))
        return mv

    def _mv_smith(self, tx, code, date, control_mode, stock_type) -> dict:
        if not self._tables_exist(["smithd", "smithm"]):
            return self._zero()
        mv = self._zero()
        for givrec, sign in (("G", -1), ("R", 1)):
            p = {"c": code, "g": givrec, "d": date}
            sf = self._stock_filter("smithd", "sd", stock_type, p)
            row = self._sum_row(tx, f"""
                SELECT SUM(COALESCE(sd.qty,0)) qty, SUM(COALESCE(sd.weight,0)) weight,
                    SUM(COALESCE({self._col_expr('smithd','stonewgt','sd')},0)) stonewgt,
                    SUM(COALESCE({self._col_expr('smithd','stoneprice','sd')},0)) stoneamt, 0 dmdwgt
                FROM smithd sd JOIN smithm sm ON sm.slno = sd.slno
                WHERE sd.code = :c AND sd.givrec = :g AND DATE(sm.tdate) <= :d
                    AND {self._control_cond('smithm','sm',control_mode)}{sf}""", p)
            self._apply(mv, self._signed(row, sign, sign, sign, sign, 0, 0))
        return mv

    def _mv_refinery(self, tx, code, date, pending, control_mode, stock_type) -> dict:
        if not self._tables_exist(["refineryd", "refinerym"]):
            return self._zero()
        mv = self._zero()
        status_op = "= 1" if pending else "<> 1"
        p = {"c": code, "d": date}
        sf = self._stock_filter("refineryd", "rd", stock_type, p)
        row = self._sum_row(tx, f"""
            SELECT SUM(COALESCE({self._col_expr('refineryd','issuedqty','rd')},0)) qty,
                SUM(COALESCE({self._col_expr('refineryd','issuedwgt','rd')},0)) weight,
                SUM(COALESCE({self._col_expr('refineryd','issuedstwgt','rd')},0)) stonewgt, 0 stoneamt, 0 dmdwgt
            FROM refineryd rd JOIN refinerym rm ON rm.slno = rd.slno
            WHERE rd.code = :c AND rm.status {status_op} AND DATE(rm.tdate) <= :d
                AND {self._control_cond('refinerym','rm',control_mode)}{sf}""", p)
        self._apply(mv, self._signed(row, -1, -1, -1, 0, 0, 0))
        p = {"c": code, "d": date}
        sf = self._stock_filter("refineryd", "rd", stock_type, p)
        row = self._sum_row(tx, f"""
            SELECT SUM(COALESCE({self._col_expr('refineryd','rcvdqty','rd')},0)) qty,
                SUM(COALESCE({self._col_expr('refineryd','rcvdwgt','rd')},0) - COALESCE({self._col_expr('refineryd','bottlestk','rd')},0) - COALESCE({self._col_expr('refineryd','testpcs','rd')},0)) weight,
                0 stonewgt, 0 stoneamt, 0 dmdwgt
            FROM refineryd rd JOIN refinerym rm ON rm.slno = rd.slno
            WHERE rd.code = :c AND rm.status {status_op} AND DATE(rm.tdate) <= :d
                AND {self._control_cond('refinerym','rm',control_mode)}{sf}""", p)
        self._apply(mv, self._signed(row, 1, 1, 0, 0, 0, 0))
        if code.strip() == "BS":
            p = {"d": date}
            sf = self._stock_filter("refineryd", "rd", stock_type, p)
            v = tx.scalar(f"""
                SELECT SUM(COALESCE({self._col_expr('refineryd','bottlestk','rd')},0))
                FROM refineryd rd JOIN refinerym rm ON rm.slno = rd.slno
                WHERE rm.status {status_op} AND DATE(rm.tdate) <= :d
                    AND {self._control_cond('refinerym','rm',control_mode)}{sf}""", p) or 0
            mv["weight"] += float(v)
        if code.strip() == "TP":
            p = {"d": date}
            sf = self._stock_filter("refineryd", "rd", stock_type, p)
            v = tx.scalar(f"""
                SELECT SUM(COALESCE({self._col_expr('refineryd','testpcs','rd')},0))
                FROM refineryd rd JOIN refinerym rm ON rm.slno = rd.slno
                WHERE rm.status {status_op} AND DATE(rm.tdate) <= :d
                    AND {self._control_cond('refinerym','rm',control_mode)}{sf}""", p) or 0
            mv["weight"] += float(v)
        return mv

    def _mv_item_adjustment(self, tx, code, date, control_mode, stock_type) -> dict:
        if not self._has("itemadj"):
            return self._zero()
        mv = self._zero()
        p = {"c": code, "d": date}
        sw = self._stock_where("itemadj", "fromstktype", stock_type, p)
        row = self._sum_row(tx, f"""
            SELECT SUM(COALESCE({self._col_expr('itemadj','fromqty')},0)) qty,
                SUM(COALESCE({self._col_expr('itemadj','fromwgt')},0)) weight,
                SUM(COALESCE({self._col_expr('itemadj','fromstwgt')},0)) stonewgt,
                SUM(COALESCE({self._col_expr('itemadj','fromstamt')},0)) stoneamt, 0 dmdwgt
            FROM itemadj WHERE fromcode = :c AND DATE(tdate) <= :d
                AND {self._control_cond('itemadj','',control_mode)}{sw}""", p)
        self._apply(mv, self._signed(row, -1, -1, -1, -1, 0, 0))
        p = {"c": code, "d": date}
        sw = self._stock_where("itemadj", "tostktype", stock_type, p)
        row = self._sum_row(tx, f"""
            SELECT SUM(COALESCE({self._col_expr('itemadj','toqty')},0)) qty,
                SUM(COALESCE({self._col_expr('itemadj','towgt')},0)) weight,
                SUM(COALESCE({self._col_expr('itemadj','tostwgt')},0)) stonewgt,
                SUM(COALESCE({self._col_expr('itemadj','tostamt')},0)) stoneamt, 0 dmdwgt
            FROM itemadj WHERE tocode = :c AND DATE(tdate) <= :d
                AND {self._control_cond('itemadj','',control_mode)}{sw}""", p)
        self._apply(mv, self._signed(row, 1, 1, 1, 1, 0, 0))
        return mv
