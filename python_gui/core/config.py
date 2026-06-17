"""Configuration loader.

Reads the EXISTING Laravel `.env` so the desktop app uses the same DB
credentials as the PHP app (HARD RULE: do not hardcode, do not re-key the DB).

Laravel reference: config/database.php -> connections.mysql reads
DB_HOST/DB_PORT/DB_DATABASE/DB_USERNAME/DB_PASSWORD, charset utf8mb4,
collation utf8mb4_unicode_ci. The secondary company DB comes from
DB_SECONDARY_DATABASE / SECONDARY_DATABASE (see .env and
app/Support/SecondaryDatabaseSync.php).

No third-party dependency here on purpose: a tiny .env parser keeps the
config layer importable for headless parity tests without GUI/DB packages.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# ----------------------------------------------------------------------------
# .env discovery + parsing
# ----------------------------------------------------------------------------

#: Candidate locations for the Laravel .env, in priority order. On the real
#: machine `python_gui/` lives inside the Laravel root, so `../.env` is the one
#: that matters. The extra paths make the loader work from a fresh checkout too.
def _env_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    pkg_root = here.parent.parent          # python_gui/
    candidates: list[Path] = []

    override = os.environ.get("GOLDAPP_ENV")
    if override:
        candidates.append(Path(override))

    candidates += [
        pkg_root.parent / ".env",          # ../.env  (Laravel root: documented layout)
        pkg_root.parent / "extracted" / ".env",  # sandbox layout in this repo
        pkg_root / ".env",                 # python_gui/.env  (local override)
        pkg_root.parent.parent / ".env",
    ]
    return candidates


def _find_env() -> Path | None:
    for path in _env_candidates():
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def parse_env(path: Path) -> dict[str, str]:
    """Parse a Laravel-style .env file.

    Handles `KEY=value`, surrounding single/double quotes, inline `# comments`
    on unquoted values, and `${VAR}` interpolation (Laravel/phpdotenv syntax).
    """
    data: dict[str, str] = {}
    raw_lines: list[tuple[str, str]] = []

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        quoted = False
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
            quoted = True
        elif "#" in value:                 # strip inline comment on bare values
            value = value.split("#", 1)[0].strip()

        raw_lines.append((key, value))
        data[key] = value
        _ = quoted  # quoting only affects comment stripping above

    # Resolve ${VAR} references (one pass is enough for this .env).
    def _resolve(val: str) -> str:
        return _VAR_RE.sub(lambda m: data.get(m.group(1), os.environ.get(m.group(1), "")), val)

    return {k: _resolve(v) for k, v in data.items()}


# ----------------------------------------------------------------------------
# Typed config
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    database: str            # primary DB (DB_DATABASE, e.g. "demo")
    username: str
    password: str
    secondary_database: str  # DB_SECONDARY_DATABASE / SECONDARY_DATABASE ("deom12")
    charset: str = "utf8mb4"
    collation: str = "utf8mb4_unicode_ci"


@dataclass(frozen=True)
class AppConfig:
    app_name: str
    env_path: Path | None
    db: DbConfig
    raw: dict[str, str]


def load_config() -> AppConfig:
    env_path = _find_env()
    env: dict[str, str] = parse_env(env_path) if env_path else {}

    # Allow process-level overrides (handy for CI / packaged builds).
    def get(key: str, default: str = "") -> str:
        return os.environ.get(key, env.get(key, default))

    db = DbConfig(
        host=get("DB_HOST", "127.0.0.1"),
        port=int(get("DB_PORT", "3306") or "3306"),
        database=get("DB_DATABASE", "demo"),
        username=get("DB_USERNAME", "root"),
        password=get("DB_PASSWORD", ""),
        secondary_database=get("DB_SECONDARY_DATABASE", get("SECONDARY_DATABASE", "")),
        charset=get("DB_CHARSET", "utf8mb4"),
        collation=get("DB_COLLATION", "utf8mb4_unicode_ci"),
    )

    return AppConfig(
        app_name=get("APP_NAME", "GoldApp"),
        env_path=env_path,
        db=db,
        raw=env,
    )


# Lazily-cached singleton -----------------------------------------------------
_CONFIG: AppConfig | None = None


def config() -> AppConfig:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_config()
    return _CONFIG


if __name__ == "__main__":
    cfg = load_config()
    print("env file :", cfg.env_path)
    print("app name :", cfg.app_name)
    print("db host  :", f"{cfg.db.host}:{cfg.db.port}")
    print("database :", cfg.db.database, "(secondary:", cfg.db.secondary_database or "-", ")")
    print("user     :", cfg.db.username, "(password set:", bool(cfg.db.password), ")")
