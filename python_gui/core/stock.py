"""Item stock movement engine — port of
StockPeriodLedgerController::calcItemStock (itself a port of the legacy
calcItemStock.php).

For one item code it computes opening (everything before ``d1``), the issued /
received movement inside ``[d1, d2]``, and the closing balance, summing signed
quantity + weight across every stock-moving table:

  out (issued):   salesd, purchaserd, smithd givrec='G', refinery issued,
                  itemadj from-side
  in (received):  salesrd, purchased,  smithd givrec='R', refinery received,
                  itemadj to-side, orderdga

Closing = opening + received - issued. ``net_wgt`` subtracts stone weight from
the weight columns; ``with_stone`` also tracks the stone-weight column. Every
table is guarded so a frozen schema missing a module's tables still computes.
"""

from __future__ import annotations

from decimal import Decimal

from .db import Database
from .decimals import weight as wq

_ZERO = Decimal("0")


class StockCalculator:
    def __init__(self, database: Database, gilevel: int = 1):
        self.db = database
        self.g = int(gilevel or 1)

    def _has(self, *tables: str) -> bool:
        return all(self.db.table_exists(t) for t in tables)

    def _one(self, sql: str, params: dict) -> dict:
        return self.db.fetchone(sql, params) or {}

    def calc_item_stock(self, scode: str, d1: str, d2: str,
                        net_wgt: bool = False, with_stone: bool = False) -> dict:
        g = self.g
        # weight fragments
        wS = "(d.weight - COALESCE(d.stonewgt,0))" if net_wgt else "d.weight"
        wP = "(d.weight - COALESCE(d.stwgt,0))" if net_wgt else "d.weight"
        wRI = "(d.issuedwgt - COALESCE(d.issuedstwgt,0))" if net_wgt else "d.issuedwgt"
        wAF = "(fromwgt - COALESCE(fromstwgt,0))" if net_wgt else "fromwgt"
        wAT = "(towgt - COALESCE(tostwgt,0))" if net_wgt else "towgt"
        wO = "(weight - COALESCE(stonewgt,0))" if net_wgt else "weight"
        sS = "COALESCE(SUM(d.stonewgt),0)" if with_stone else "0"
        sP = "COALESCE(SUM(d.stwgt),0)" if with_stone else "0"
        sAF = "fromstwgt" if with_stone else "0"
        sAT = "tostwgt" if with_stone else "0"
        sO = "COALESCE(SUM(stonewgt),0)" if with_stone else "0"

        opq = 0; opw = _ZERO; ops = _ZERO

        # opening base from items
        if self.db.table_exists("items"):
            qc = "opqty" if g == 1 else "opqtyb"
            wc = "opweight" if g == 1 else "opweightb"
            sc = "opstonewgt" if g == 1 else "opstonewgtb"
            row = self.db.fetchone("SELECT * FROM items WHERE code = :c LIMIT 1", {"c": scode}) or {}
            if row:
                if qc in row: opq += int(row.get(qc) or 0)
                if wc in row: opw += wq(row.get(wc))
                if net_wgt and sc in row: opw -= wq(row.get(sc))
                if with_stone and sc in row: ops += wq(row.get(sc))

        def acc(qd, wd, sd, q, w, s, sign):
            return qd + sign * int(q or 0), wd + sign * wq(w), sd + sign * wq(s)

        # ── pre-period (< d1) opening adjustments ──
        opq, opw, ops = self._movement(scode, "<", d1, None, opq, opw, ops, acc,
                                       wS, wP, wRI, wAF, wAT, wO, sS, sP, sAF, sAT, sO,
                                       opening=True)

        # ── within period [d1, d2] ──
        iq = 0; iw = _ZERO; isw = _ZERO  # issued / out
        rq = 0; rw = _ZERO; rsw = _ZERO  # received / in
        agg = self._period(scode, d1, d2, wS, wP, wRI, wAF, wAT, wO, sS, sP, sAF, sAT, sO)
        iq, iw, isw = agg["issued"]
        rq, rw, rsw = agg["received"]

        clq = opq + rq - iq
        clw = opw + rw - iw
        cls = ops + rsw - isw
        return {
            "opqty": opq, "opwgt": wq(opw), "opswgt": wq(ops),
            "issuedqty": iq, "issuedwgt": wq(iw), "issuedswgt": wq(isw),
            "rcvdqty": rq, "rcvdwgt": wq(rw), "rcvdswgt": wq(rsw),
            "clqty": clq, "clwgt": wq(clw), "clswgt": wq(cls),
        }

    # opening accumulation (< d1)
    def _movement(self, scode, op, d1, d2, opq, opw, ops, acc,
                  wS, wP, wRI, wAF, wAT, wO, sS, sP, sAF, sAT, sO, opening):
        g = self.g
        dcond = "m.tdate < :d1"
        p = {"c": scode, "g": g, "d1": d1}
        st = "COALESCE(m.status,1) <> 0"
        if self._has("salesd", "salesm"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wS}),0) w, {sS} s "
                          f"FROM salesd d JOIN salesm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g "
                          f"AND {st} AND {dcond} AND (TRIM(d.jcode)='' OR d.jcode IS NULL)", p)
            opq, opw, ops = acc(opq, opw, ops, r["q"], r["w"], r["s"], -1)
        if self._has("salesrd", "salesrm"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wS}),0) w, {sS} s "
                          f"FROM salesrd d JOIN salesrm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g AND {st} AND {dcond}", p)
            opq, opw, ops = acc(opq, opw, ops, r["q"], r["w"], r["s"], +1)
        if self._has("purchased", "purchasem"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wP}),0) w, {sP} s "
                          f"FROM purchased d JOIN purchasem m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g AND {st} AND {dcond}", p)
            opq, opw, ops = acc(opq, opw, ops, r["q"], r["w"], r["s"], +1)
        if self._has("purchaserd", "purchaserm"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wP}),0) w, {sP} s "
                          f"FROM purchaserd d JOIN purchaserm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g AND {st} AND {dcond}", p)
            opq, opw, ops = acc(opq, opw, ops, r["q"], r["w"], r["s"], -1)
        if self._has("smithd", "smithm"):
            for gr, sign in (("G", -1), ("R", +1)):
                r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wS}),0) w, {sS} s "
                              f"FROM smithd d JOIN smithm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g "
                              f"AND {st} AND d.givrec=:gr AND {dcond}", {**p, "gr": gr})
                opq, opw, ops = acc(opq, opw, ops, r["q"], r["w"], r["s"], sign)
        if self._has("refineryd", "refinerym"):
            r = self._one(f"SELECT COALESCE(SUM(d.issuedqty),0) iq, COALESCE(SUM({wRI}),0) iw, "
                          f"COALESCE(SUM(d.rcvdqty),0) rq, "
                          f"COALESCE(SUM(COALESCE(d.ao, d.rcvdwgt-d.bottlestk-d.testpcs, d.rcvdwgt)),0) rw "
                          f"FROM refineryd d JOIN refinerym m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g AND {st} AND {dcond}", p)
            opq, opw, ops = acc(opq, opw, ops, r["iq"], r["iw"], 0, -1)
            opq, opw, ops = acc(opq, opw, ops, r["rq"], r["rw"], 0, +1)
        if self.db.table_exists("itemadj"):
            r = self._one(f"SELECT COALESCE(SUM(CASE WHEN fromcode=:c THEN fromqty ELSE 0 END),0) fq, "
                          f"COALESCE(SUM(CASE WHEN fromcode=:c THEN {wAF} ELSE 0 END),0) fw, "
                          f"COALESCE(SUM(CASE WHEN fromcode=:c THEN {sAF} ELSE 0 END),0) fs, "
                          f"COALESCE(SUM(CASE WHEN tocode=:c THEN toqty ELSE 0 END),0) tq, "
                          f"COALESCE(SUM(CASE WHEN tocode=:c THEN {wAT} ELSE 0 END),0) tw, "
                          f"COALESCE(SUM(CASE WHEN tocode=:c THEN {sAT} ELSE 0 END),0) ts "
                          f"FROM itemadj WHERE control<=:g AND tdate < :d1", p)
            opq, opw, ops = acc(opq, opw, ops, r["fq"], r["fw"], r["fs"], -1)
            opq, opw, ops = acc(opq, opw, ops, r["tq"], r["tw"], r["ts"], +1)
        if self._has("orderdga", "orderm"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wO}),0) w, {sO} s "
                          f"FROM orderdga d JOIN orderm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g AND {st} AND {dcond}", p)
            opq, opw, ops = acc(opq, opw, ops, r["q"], r["w"], r["s"], +1)
        return opq, opw, ops

    # within-period issued/received split
    def _period(self, scode, d1, d2, wS, wP, wRI, wAF, wAT, wO, sS, sP, sAF, sAT, sO):
        g = self.g
        p = {"c": scode, "g": g, "d1": d1, "d2": d2}
        st = "COALESCE(m.status,1) <> 0"
        dr = "m.tdate >= :d1 AND m.tdate <= :d2"
        iq = 0; iw = _ZERO; isw = _ZERO
        rq = 0; rw = _ZERO; rsw = _ZERO

        def add_i(q, w, s):
            nonlocal iq, iw, isw
            iq += int(q or 0); iw += wq(w); isw += wq(s)

        def add_r(q, w, s):
            nonlocal rq, rw, rsw
            rq += int(q or 0); rw += wq(w); rsw += wq(s)

        if self._has("salesd", "salesm"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wS}),0) w, {sS} s "
                          f"FROM salesd d JOIN salesm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g "
                          f"AND {st} AND {dr} AND (TRIM(d.jcode)='' OR d.jcode IS NULL)", p)
            add_i(r["q"], r["w"], r["s"])
        if self._has("salesrd", "salesrm"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wS}),0) w, {sS} s "
                          f"FROM salesrd d JOIN salesrm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g AND {st} AND {dr}", p)
            add_r(r["q"], r["w"], r["s"])
        if self._has("purchased", "purchasem"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wP}),0) w, {sP} s "
                          f"FROM purchased d JOIN purchasem m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g AND {st} AND {dr}", p)
            add_r(r["q"], r["w"], r["s"])
        if self._has("purchaserd", "purchaserm"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wP}),0) w, {sP} s "
                          f"FROM purchaserd d JOIN purchaserm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g AND {st} AND {dr}", p)
            add_i(r["q"], r["w"], r["s"])
        if self._has("smithd", "smithm"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wS}),0) w, {sS} s "
                          f"FROM smithd d JOIN smithm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g "
                          f"AND {st} AND d.givrec='G' AND {dr}", p)
            add_i(r["q"], r["w"], r["s"])
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wS}),0) w, {sS} s "
                          f"FROM smithd d JOIN smithm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g "
                          f"AND {st} AND d.givrec='R' AND {dr}", p)
            add_r(r["q"], r["w"], r["s"])
        if self._has("refineryd", "refinerym"):
            r = self._one(f"SELECT COALESCE(SUM(d.issuedqty),0) iq, COALESCE(SUM({wRI}),0) iw, "
                          f"COALESCE(SUM(d.rcvdqty),0) rq, "
                          f"COALESCE(SUM(COALESCE(d.ao, d.rcvdwgt-d.bottlestk-d.testpcs, d.rcvdwgt)),0) rw "
                          f"FROM refineryd d JOIN refinerym m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g AND {st} AND {dr}", p)
            add_i(r["iq"], r["iw"], 0)
            add_r(r["rq"], r["rw"], 0)
        if self.db.table_exists("itemadj"):
            r = self._one(f"SELECT COALESCE(SUM(CASE WHEN fromcode=:c THEN fromqty ELSE 0 END),0) fq, "
                          f"COALESCE(SUM(CASE WHEN fromcode=:c THEN {wAF} ELSE 0 END),0) fw, "
                          f"COALESCE(SUM(CASE WHEN fromcode=:c THEN {sAF} ELSE 0 END),0) fs, "
                          f"COALESCE(SUM(CASE WHEN tocode=:c THEN toqty ELSE 0 END),0) tq, "
                          f"COALESCE(SUM(CASE WHEN tocode=:c THEN {wAT} ELSE 0 END),0) tw, "
                          f"COALESCE(SUM(CASE WHEN tocode=:c THEN {sAT} ELSE 0 END),0) ts "
                          f"FROM itemadj WHERE control<=:g AND tdate >= :d1 AND tdate <= :d2", p)
            add_i(r["fq"], r["fw"], r["fs"])
            add_r(r["tq"], r["tw"], r["ts"])
        if self._has("orderdga", "orderm"):
            r = self._one(f"SELECT COALESCE(SUM(d.qty),0) q, COALESCE(SUM({wO}),0) w, {sO} s "
                          f"FROM orderdga d JOIN orderm m ON m.slno=d.slno WHERE d.code=:c AND m.control<=:g AND {st} AND {dr}", p)
            add_r(r["q"], r["w"], r["s"])
        return {"issued": (iq, iw, isw), "received": (rq, rw, rsw)}
