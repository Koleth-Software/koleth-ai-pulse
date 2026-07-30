from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised only without Postgres extras installed.
    psycopg = None
    dict_row = None


DEFAULT_DB_PATH = Path("data/koleth-ai-pulse.db")
POSTGRES_SCHEMES = ("postgres://", "postgresql://")
NAMED_PARAM_RE = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


@dataclass(frozen=True)
class NewsItem:
    kaynak: str
    kategori: str
    dil: str
    baslik: str
    ozet: str | None
    link: str
    yayin_tarihi: str | None = None
    image_url: str | None = None


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS haberler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kaynak TEXT NOT NULL,
    kategori TEXT NOT NULL DEFAULT 'genel',
    dil TEXT NOT NULL DEFAULT 'tr',
    baslik TEXT NOT NULL,
    ozet TEXT,
    link TEXT UNIQUE NOT NULL,
    image_url TEXT,
    yayin_tarihi TEXT,
    eklenme_tarihi TEXT DEFAULT CURRENT_TIMESTAMP,
    discord_gonderildi INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_haberler_eklenme_tarihi
    ON haberler (eklenme_tarihi DESC);
CREATE INDEX IF NOT EXISTS idx_haberler_kaynak
    ON haberler (kaynak);
CREATE INDEX IF NOT EXISTS idx_haberler_kategori
    ON haberler (kategori);
CREATE INDEX IF NOT EXISTS idx_haberler_dil
    ON haberler (dil);
CREATE INDEX IF NOT EXISTS idx_haberler_discord
    ON haberler (discord_gonderildi, eklenme_tarihi DESC);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS haberler (
    id BIGSERIAL PRIMARY KEY,
    kaynak TEXT NOT NULL,
    kategori TEXT NOT NULL DEFAULT 'genel',
    dil TEXT NOT NULL DEFAULT 'tr',
    baslik TEXT NOT NULL,
    ozet TEXT,
    link TEXT UNIQUE NOT NULL,
    image_url TEXT,
    yayin_tarihi TIMESTAMPTZ,
    eklenme_tarihi TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    discord_gonderildi BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_haberler_eklenme_tarihi
    ON haberler (eklenme_tarihi DESC);
CREATE INDEX IF NOT EXISTS idx_haberler_kaynak
    ON haberler (kaynak);
CREATE INDEX IF NOT EXISTS idx_haberler_kategori
    ON haberler (kategori);
CREATE INDEX IF NOT EXISTS idx_haberler_dil
    ON haberler (dil);
CREATE INDEX IF NOT EXISTS idx_haberler_discord
    ON haberler (discord_gonderildi, eklenme_tarihi DESC);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def is_postgres_url(value: str | os.PathLike[str] | None) -> bool:
    return str(value or "").startswith(POSTGRES_SCHEMES)


def is_postgres_connection(conn: Any) -> bool:
    return conn.__class__.__module__.startswith("psycopg")


def resolve_db_path(db_path: str | os.PathLike[str] | None = None) -> Path:
    return Path(db_path) if db_path else Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH)))


def sqlite_connect(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def postgres_connect(url: str):
    if psycopg is None or dict_row is None:
        raise RuntimeError("Postgres kullanmak için psycopg paketi kurulmalı")
    return psycopg.connect(url, row_factory=dict_row)


def connect(db_path: str | os.PathLike[str] | None = None):
    target = str(db_path or database_url())
    if is_postgres_url(target):
        return postgres_connect(target)
    return sqlite_connect(db_path)


@contextmanager
def db_session(db_path: str | os.PathLike[str] | None = None) -> Iterator[Any]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def postgres_sql(sql: str) -> str:
    return NAMED_PARAM_RE.sub(r"%(\1)s", sql)


def execute(conn: Any, sql: str, params: dict[str, Any] | None = None):
    if is_postgres_connection(conn):
        return conn.execute(postgres_sql(sql), params or {})
    return conn.execute(sql, params or {})


def execute_schema(conn: Any, schema: str) -> None:
    if is_postgres_connection(conn):
        with conn.cursor() as cursor:
            for statement in schema.split(";"):
                if statement.strip():
                    cursor.execute(statement)
        return
    conn.executescript(schema)


def init_db(conn: Any) -> None:
    if is_postgres_connection(conn):
        execute_schema(conn, POSTGRES_SCHEMA)
    else:
        execute_schema(conn, SQLITE_SCHEMA)
        ensure_column(conn, "haberler", "image_url", "TEXT")
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def insert_news(conn: Any, item: NewsItem) -> bool:
    payload = asdict(item)
    if is_postgres_connection(conn):
        cursor = execute(
            conn,
            """
            INSERT INTO haberler
                (kaynak, kategori, dil, baslik, ozet, link, image_url, yayin_tarihi)
            VALUES
                (:kaynak, :kategori, :dil, :baslik, :ozet, :link, :image_url, :yayin_tarihi)
            ON CONFLICT (link) DO NOTHING
            """,
            payload,
        )
    else:
        cursor = execute(
            conn,
            """
            INSERT OR IGNORE INTO haberler
                (kaynak, kategori, dil, baslik, ozet, link, image_url, yayin_tarihi)
            VALUES
                (:kaynak, :kategori, :dil, :baslik, :ozet, :link, :image_url, :yayin_tarihi)
            """,
            payload,
        )
    conn.commit()
    return cursor.rowcount > 0


def list_news(
    conn: Any,
    *,
    limit: int = 25,
    offset: int = 0,
    kaynak: str | None = None,
    kategori: str | None = None,
    dil: str | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    where: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if kaynak:
        where.append("kaynak = :kaynak")
        params["kaynak"] = kaynak
    if kategori:
        where.append("kategori = :kategori")
        params["kategori"] = kategori
    if dil:
        where.append("dil = :dil")
        params["dil"] = dil

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = execute(
        conn,
        f"""
        SELECT id, kaynak, kategori, dil, baslik, ozet, link, image_url,
               yayin_tarihi, eklenme_tarihi, discord_gonderildi
        FROM haberler
        {where_sql}
        ORDER BY COALESCE(yayin_tarihi, eklenme_tarihi) DESC, id DESC
        LIMIT :limit OFFSET :offset
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def list_unsent_for_discord(
    conn: Any,
    *,
    limit: int = 20,
    dil: str | None = None,
    kategori: str | None = None,
    require_image: bool = False,
) -> list[dict[str, Any]]:
    where = ["discord_gonderildi = 0"]
    params: dict[str, Any] = {"limit": max(1, min(limit, 100))}
    if dil:
        where.append("dil = :dil")
        params["dil"] = dil
    if kategori:
        where.append("kategori = :kategori")
        params["kategori"] = kategori
    if require_image:
        where.append("image_url IS NOT NULL")
        where.append("image_url != ''")

    rows = execute(
        conn,
        f"""
        SELECT id, kaynak, kategori, dil, baslik, ozet, link, image_url,
               yayin_tarihi, eklenme_tarihi, discord_gonderildi
        FROM haberler
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(yayin_tarihi, eklenme_tarihi) ASC, id ASC
        LIMIT :limit
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def mark_discord_sent(conn: Any, news_id: int) -> bool:
    cursor = execute(
        conn,
        "UPDATE haberler SET discord_gonderildi = 1 WHERE id = :id",
        {"id": news_id},
    )
    conn.commit()
    return cursor.rowcount > 0


def source_counts(conn: Any) -> list[dict[str, Any]]:
    rows = execute(
        conn,
        """
        SELECT kaynak, kategori, dil, COUNT(*) AS haber_sayisi
        FROM haberler
        GROUP BY kaynak, kategori, dil
        ORDER BY haber_sayisi DESC, kaynak ASC
        """,
    ).fetchall()
    return [dict(row) for row in rows]


def load_settings(conn: Any, namespace: str) -> dict[str, Any]:
    prefix = f"{namespace}."
    rows = execute(
        conn,
        "SELECT key, value FROM app_settings WHERE key LIKE :prefix",
        {"prefix": f"{prefix}%"},
    ).fetchall()
    settings: dict[str, Any] = {}
    for row in rows:
        key = str(row["key"])[len(prefix) :]
        try:
            settings[key] = json.loads(row["value"])
        except json.JSONDecodeError:
            settings[key] = row["value"]
    return settings


def save_settings(conn: Any, namespace: str, settings: dict[str, Any]) -> None:
    for key, value in settings.items():
        full_key = f"{namespace}.{key}"
        payload = json.dumps(value, ensure_ascii=False)
        if is_postgres_connection(conn):
            execute(
                conn,
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (:key, :value, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
                """,
                {"key": full_key, "value": payload},
            )
        else:
            execute(
                conn,
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (:key, :value, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE
                    SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                {"key": full_key, "value": payload},
            )
    conn.commit()
