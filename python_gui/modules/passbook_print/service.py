"""Passbook Print — port of ``PassbookPrintController`` (scheme/kuri passbook).

Continuation printing for a party's scheme/kuri collection book: it reads
``kuricolln`` rows from the last printed point (``clients.lpslno``), pads the
start with blank lines so printing resumes on the right line of a pre-printed
book, optionally inserts blank lines across a page fold, and — crucially —
*advances the party's print cursor* (``clients.lpline/lpslno/lpsno``) so the
next run continues where this one stopped. That cursor write is the stateful
behaviour worth porting precisely; it runs in one transaction.
"""

from __future__ import annotations

from ...core.db import Database
from ...core.decimals import money, quantize, to_decimal, weight

_GROUPS = {"scheme": "SCHM", "kuri": "KC"}


class PassbookPrintError(Exception):
    pass


class PassbookPrintService:
    def __init__(self, database: Database):
        self.db = database

    def mode_group(self, mode: str) -> str:
        return _GROUPS.get(str(mode or "scheme").strip().lower(), _GROUPS["scheme"])

    def party_lookup(self, code: str) -> dict:
        code = str(code or "").strip().upper()
        if not code:
            raise PassbookPrintError("Party code required")
        client = self.db.fetchone("SELECT * FROM clients WHERE TRIM(code) = :c", {"c": code}) \
            if self.db.table_exists("clients") else None
        if not client:
            raise PassbookPrintError("Party not found")
        last_slno = int(to_decimal(client.get("lpslno")) or 0)
        last_line = int(to_decimal(client.get("lpline")) or 0)
        last_no = int(to_decimal(client.get("lpsno")) or 0)
        next_doc = ""
        if self.db.table_exists("kuricolln"):
            next_doc = str(self.db.scalar(
                "SELECT docno FROM kuricolln WHERE TRIM(code) = :c AND slno > :s ORDER BY slno LIMIT 1",
                {"c": code, "s": last_slno}) or "").strip()
        return {
            "code": code, "address": self._address(client),
            "start_line": last_line + 1, "start_docno": next_doc,
            "start_slno": last_no + 1, "last_print_slno": last_slno,
        }

    def build(self, code: str, *, date1: str = "", date2: str = "", start_line: int = 1,
              start_docno: str = "", start_slno_no: int = 1, reset: bool = False,
              lines_per_page: int = 0, lines_half_page: int = 0, skip_middle: int = 0) -> dict:
        code = str(code or "").strip().upper()
        if not code:
            raise PassbookPrintError("Party code required")
        if not self.db.table_exists("clients"):
            raise PassbookPrintError("Party not found")
        start_line = max(1, int(start_line or 1))
        start_slno_no = max(1, int(start_slno_no or 1))
        lines_per_page = max(0, int(lines_per_page or 0))
        lines_half_page = max(0, int(lines_half_page or 0))
        skip_middle = max(0, int(skip_middle or 0))

        with self.db.transaction() as tx:
            client = tx.fetchall("SELECT * FROM clients WHERE TRIM(code) = :c", {"c": code})
            if not client:
                raise PassbookPrintError("Party not found")
            client = client[0]

            start_slno = 0 if reset else int(to_decimal(client.get("lpslno")) or 0) + 1
            if str(start_docno or "").strip() and self.db.table_exists("kuricolln"):
                doc_slno = int(to_decimal(tx.scalar(
                    "SELECT slno FROM kuricolln WHERE TRIM(code) = :c AND TRIM(COALESCE(docno,'')) = :d",
                    {"c": code, "d": str(start_docno).strip()})) or 0)
                if doc_slno > 0:
                    start_slno = doc_slno
            if not reset and start_slno <= 0:
                start_slno = max(1, int(to_decimal(client.get("lpslno")) or 0) + 1)

            if not self.db.table_exists("kuricolln"):
                raise PassbookPrintError("Collection table not found")

            where = ["TRIM(code) = :c"]
            params = {"c": code}
            if start_slno > 0:
                where.append("slno >= :ss"); params["ss"] = start_slno
            if str(date1 or "").strip():
                where.append("tdate >= :d1"); params["d1"] = str(date1).strip()
            if str(date2 or "").strip():
                where.append("tdate <= :d2"); params["d2"] = str(date2).strip()
            entries = tx.fetchall(
                f"SELECT slno, tdate, COALESCE(docno,'') AS docno, COALESCE(rcptno,'') AS rcptno, "
                f"COALESCE(amount,0) AS amount, COALESCE(grate,0) AS grate, COALESCE(wgt,0) AS wgt, "
                f"COALESCE(agent,'') AS agent FROM kuricolln WHERE {' AND '.join(where)} "
                f"ORDER BY tdate, slno", params)
            if not entries:
                raise PassbookPrintError("Nothing to print more")

            rows: list[dict] = [{"blank": True} for _ in range(1, start_line)]
            tno = start_slno_no
            last_slno = 0
            for e in entries:
                rows.append({
                    "blank": False, "tdate": str(e.get("tdate") or "").strip(),
                    "docno": str(e.get("docno") or "").strip(), "rcptno": str(e.get("rcptno") or "").strip(),
                    "rate": money(e.get("grate")), "amount": money(e.get("amount")),
                    "wgt": weight(e.get("wgt")), "slno": int(e["slno"]), "tno": tno,
                    "agent": str(e.get("agent") or "").strip(),
                })
                last_slno = int(e["slno"])
                tno += 1
                line_count = len(rows)
                if lines_half_page > 0 and lines_per_page > 0 and skip_middle > 0:
                    if line_count % lines_half_page == 0 and line_count % lines_per_page <= lines_half_page:
                        for _ in range(skip_middle):
                            rows.append({"blank": True, "slno": last_slno})

            last_line_no = (len(rows) % lines_per_page) if (rows and lines_per_page > 0) else len(rows)
            last_passbook_no = tno - 1

            tx.execute(
                "UPDATE clients SET lpline = :ll, lpslno = :ls, lpsno = :ln WHERE TRIM(code) = :c",
                {"ll": last_line_no, "ls": last_slno, "ln": last_passbook_no, "c": code})

            return {
                "party": {"code": code, "address": self._address(client)}, "rows": rows,
                "summary": {"last_line": last_line_no, "last_slno": last_slno,
                            "last_passbook_no": last_passbook_no},
            }

    def _address(self, client: dict) -> str:
        parts = [str(client.get(k) or "").strip() for k in ("addr1", "addr2", "addr3")]
        return " ".join(p for p in parts if p)
