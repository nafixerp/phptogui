"""Database access layer.

SQLAlchemy Core over mysql-connector-python, pointed at the SAME frozen MySQL
schema the Laravel app uses (config/database.php -> mysql connection). We keep
raw parameterised SQL — `text()` with bound params — because the Laravel
queries we port are non-trivial and we must preserve exact column names and
posting math (HARD RULE 2).

Company selection (CompanySelectController) switches the active database name at
runtime; Laravel does `Config::set('database.connections.mysql.database', $db);
DB::purge('mysql'); DB::reconnect('mysql');` — we mirror that by disposing the
engine and rebuilding it against the new database (see `Database.use_database`).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import quote_plus

from .config import DbConfig, config

# SQLAlchemy / driver are imported lazily so core.config and core.crypto stay
# importable for headless parity tests without these packages installed.
try:  # pragma: no cover - import guard
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
    _SA_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    create_engine = None  # type: ignore
    text = None  # type: ignore
    Engine = Any  # type: ignore
    _SA_IMPORT_ERROR = exc


def _require_sqlalchemy() -> None:
    if _SA_IMPORT_ERROR is not None:
        raise RuntimeError(
            "SQLAlchemy / mysql-connector-python are not installed. "
            "Run: pip install -r python_gui/requirements.txt"
        ) from _SA_IMPORT_ERROR


def build_url(db: DbConfig, database: str | None = None) -> str:
    """mysql+mysqlconnector URL. Empty password (XAMPP root) is supported."""
    name = database if database is not None else db.database
    auth = quote_plus(db.username)
    if db.password:
        auth += ":" + quote_plus(db.password)
    return (
        f"mysql+mysqlconnector://{auth}@{db.host}:{db.port}/{name}"
        f"?charset={db.charset}"
    )


class Tx:
    """A bound connection inside an open transaction (see Database.transaction)."""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql: str, params: Mapping[str, Any] | None = None):
        return self.conn.execute(text(sql), params or {})

    def scalar(self, sql: str, params: Mapping[str, Any] | None = None) -> Any:
        return self.conn.execute(text(sql), params or {}).scalar()


class Database:
    """Thin engine holder with helpers and runtime DB switching."""

    def __init__(self, db_config: DbConfig | None = None, database: str | None = None):
        self.cfg = db_config or config().db
        self.database = database or self.cfg.database
        self._engine: Engine | None = None

    # -- engine lifecycle ---------------------------------------------------
    @property
    def engine(self) -> Engine:
        _require_sqlalchemy()
        if self._engine is None:
            self._engine = create_engine(
                build_url(self.cfg, self.database),
                pool_pre_ping=True,
                pool_recycle=1800,
                future=True,
            )
        return self._engine

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def use_database(self, database: str) -> None:
        """Company switch — rebuild the engine against another DB (frozen schema)."""
        if database and database != self.database:
            self.dispose()
            self.database = database

    # -- query helpers ------------------------------------------------------
    def fetchall(self, sql: str, params: Mapping[str, Any] | None = None) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params or {})
            return [dict(r) for r in rows.mappings()]

    def fetchone(self, sql: str, params: Mapping[str, Any] | None = None) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), params or {}).mappings().first()
            return dict(row) if row else None

    def scalar(self, sql: str, params: Mapping[str, Any] | None = None) -> Any:
        with self.engine.connect() as conn:
            return conn.execute(text(sql), params or {}).scalar()

    def execute(self, sql: str, params: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None):
        """Run a single write inside its own transaction (commit/rollback handled)."""
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params or {})

    @contextmanager
    def transaction(self) -> "Iterator[Tx]":
        """Group several writes atomically — mirrors Laravel's DB::transaction().

        Usage:
            with db.transaction() as tx:
                tx.execute("INSERT ...", {...})
                tx.execute("UPDATE ...", {...})
        """
        with self.engine.begin() as conn:
            yield Tx(conn)

    def table_exists(self, table: str) -> bool:
        row = self.fetchone(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :db AND table_name = :t LIMIT 1",
            {"db": self.database, "t": table},
        )
        return row is not None

    def column_exists(self, table: str, column: str) -> bool:
        row = self.fetchone(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :db AND table_name = :t AND column_name = :c LIMIT 1",
            {"db": self.database, "t": table, "c": column},
        )
        return row is not None

    def columns(self, table: str) -> list[str]:
        """Lower-cased column names for a table (empty list if table absent)."""
        rows = self.fetchall(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :db AND table_name = :t",
            {"db": self.database, "t": table},
        )
        return [str(next(iter(r.values()))).lower() for r in rows]

    def list_databases(self) -> list[str]:
        """For the company selector. Mirrors CompanySelectController's SHOW DATABASES."""
        rows = self.fetchall("SHOW DATABASES")
        out = []
        for r in rows:
            name = next(iter(r.values()))
            if name not in ("information_schema", "performance_schema", "mysql", "sys"):
                out.append(str(name))
        return out

    # -- connectivity probe -------------------------------------------------
    def check_connection(self) -> tuple[bool, str]:
        try:
            self.scalar("SELECT 1")
            return True, f"Connected to {self.cfg.host}:{self.cfg.port}/{self.database}"
        except Exception as exc:  # surface a readable message to the login UI
            return False, str(exc).splitlines()[0]


# Module-level primary handle (company switch mutates this instance).
_DB: Database | None = None


def db() -> Database:
    global _DB
    if _DB is None:
        _DB = Database()
    return _DB


def secondary_db() -> Database | None:
    """Secondary company DB ("deom12") if configured; else None."""
    cfg = config().db
    if not cfg.secondary_database:
        return None
    return Database(cfg, cfg.secondary_database)
