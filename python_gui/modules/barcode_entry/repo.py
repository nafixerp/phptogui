"""Barcode Entry repository — `barcode` table. Source: BarcodeEntryController.

One row per jewellery item. The row is column-filtered to the live schema.
Next barcode = max(bcode)+1 (BCMaxNo='Y') or generali.BCNO+1, min 100001.
Delete is blocked when the barcode has been sold (`salesd.bcode`).
"""

from __future__ import annotations

from ...core.db import Database


class BarcodeRepo:
    def __init__(self, database: Database):
        self.db = database

    def has_table(self, t: str = "barcode") -> bool:
        return self.db.table_exists(t)

    def columns(self) -> set[str]:
        return set(self.db.columns("barcode"))

    def filter_columns(self, row: dict) -> dict:
        cols = self.columns()
        return {k: v for k, v in row.items() if k.lower() in cols}

    def exists(self, bcode: int) -> bool:
        return self.db.fetchone("SELECT 1 FROM barcode WHERE bcode = :b LIMIT 1", {"b": bcode}) is not None

    def get(self, bcode: int) -> dict | None:
        return self.db.fetchone("SELECT * FROM barcode WHERE bcode = :b LIMIT 1", {"b": bcode})

    def max_bcode(self) -> int:
        if not self.has_table():
            return 0
        return int(self.db.scalar("SELECT COALESCE(MAX(bcode), 0) FROM barcode") or 0)

    def generali_bcno(self) -> int:
        v = self.db.scalar("SELECT cvalue FROM generali WHERE code = 'BCNO' LIMIT 1")
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    def set_bcno(self, bcode: int) -> None:
        res = self.db.execute("UPDATE generali SET cvalue = :v WHERE code = 'BCNO'", {"v": bcode})
        if getattr(res, "rowcount", 0) == 0:
            self.db.execute("INSERT INTO generali (code, cvalue) VALUES ('BCNO', :v)", {"v": bcode})

    def load_item(self, icode: str) -> dict | None:
        if not self.db.table_exists("items"):
            return None
        return self.db.fetchone(
            "SELECT TRIM(code) AS code, name, wastage, mcharge, vaperc, stkinnos, nodisc, "
            "stickerwgt, defquality, subgrpcode FROM items WHERE UPPER(TRIM(code)) = :c LIMIT 1",
            {"c": icode.strip().upper()},
        )

    def sold(self, bcode: int) -> bool:
        if not self.db.table_exists("salesd"):
            return False
        return self.db.fetchone("SELECT 1 FROM salesd WHERE bcode = :b LIMIT 1", {"b": bcode}) is not None

    def search(self, term: str, limit: int = 200) -> list[dict]:
        sql = "SELECT bcode, icode, qty, weight, qtype, docno, stk FROM barcode"
        params: dict = {}
        if term:
            params["s"] = f"%{term}%"
            sql += " WHERE CAST(bcode AS CHAR) LIKE :s OR icode LIKE :s OR docno LIKE :s"
        sql += " ORDER BY bcode DESC LIMIT :lim"
        params["lim"] = limit
        return self.db.fetchall(sql, params)

    def insert(self, row: dict) -> None:
        cols = ", ".join(row)
        binds = ", ".join(f":{k}" for k in row)
        self.db.execute(f"INSERT INTO barcode ({cols}) VALUES ({binds})", row)

    def update(self, bcode: int, row: dict) -> None:
        upd = {k: v for k, v in row.items() if k != "bcode"}
        sets = ", ".join(f"{k} = :{k}" for k in upd)
        upd["_b"] = bcode
        self.db.execute(f"UPDATE barcode SET {sets} WHERE bcode = :_b", upd)

    def delete(self, bcode: int) -> None:
        self.db.execute("DELETE FROM barcode WHERE bcode = :b", {"b": bcode})
        for t in ("barcodedmd", "barcode_dmddet"):
            if self.db.table_exists(t):
                self.db.execute(f"DELETE FROM {t} WHERE bcode = :b", {"b": bcode})
