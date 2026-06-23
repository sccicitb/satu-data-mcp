from __future__ import annotations

import asyncio
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .api_client import SatuDataClient
from .config import CATALOG_DB_PATH, CATALOG_REFRESH_INTERVAL_SECONDS
from .textutils import strip_html

_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    slug TEXT PRIMARY KEY,
    judul TEXT,
    deskripsi TEXT,
    grup TEXT,
    opd TEXT,
    first_year INTEGER,
    last_year INTEGER,
    total_data INTEGER,
    total_views INTEGER,
    total_download INTEGER,
    updated_at TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS datasets_fts USING fts5(
    slug UNINDEXED, judul, deskripsi, grup, opd
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(CATALOG_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_stale() -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'last_refresh'").fetchone()
        if row is None:
            return True
        return (time.time() - float(row["value"])) > CATALOG_REFRESH_INTERVAL_SECONDS


def row_count() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM datasets").fetchone()["c"]


async def refresh_catalog(client: SatuDataClient) -> int:
    """Page through the full /datasets listing and rebuild the local catalog.

    672 datasets at 10/page is ~68 requests - a few seconds. Doing a full
    rebuild each refresh is simpler than diffing and the dataset is small
    enough that it's cheap.
    """
    first = await client.list_datasets(page=1)
    pagination = first["datasets"]
    last_page = pagination["last_page"]
    all_rows: list[dict[str, Any]] = list(pagination["data"])

    for page in range(2, last_page + 1):
        await asyncio.sleep(0.2)  # stay under the API's burst rate limit
        payload = await client.list_datasets(page=page)
        all_rows.extend(payload["datasets"]["data"])

    with _connect() as conn:
        conn.execute("DELETE FROM datasets")
        conn.execute("DELETE FROM datasets_fts")
        for item in all_rows:
            slug = item["slug"]
            judul = item.get("judul", "")
            deskripsi = strip_html(item.get("deskripsi"))
            grup = (item.get("grup") or {}).get("name", "")
            opd = (item.get("opd") or {}).get("name", "")
            conn.execute(
                """
                INSERT INTO datasets
                    (slug, judul, deskripsi, grup, opd, first_year, last_year,
                     total_data, total_views, total_download, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    judul=excluded.judul, deskripsi=excluded.deskripsi,
                    grup=excluded.grup, opd=excluded.opd,
                    first_year=excluded.first_year, last_year=excluded.last_year,
                    total_data=excluded.total_data, total_views=excluded.total_views,
                    total_download=excluded.total_download, updated_at=excluded.updated_at
                """,
                (
                    slug, judul, deskripsi, grup, opd,
                    item.get("first_year"), item.get("last_year"),
                    item.get("total_data"), item.get("total_views"),
                    item.get("total_download"), item.get("updated_at"),
                ),
            )
            conn.execute(
                "INSERT INTO datasets_fts (slug, judul, deskripsi, grup, opd) VALUES (?, ?, ?, ?, ?)",
                (slug, judul, deskripsi, grup, opd),
            )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('last_refresh', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(time.time()),),
        )
    return len(all_rows)


def search_catalog(
    query: str | None = None,
    grup: str | None = None,
    opd: str | None = None,
    tahun: int | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    offset = (page - 1) * page_size
    with _connect() as conn:
        if query:
            sql = """
                SELECT d.* FROM datasets d
                JOIN datasets_fts f ON f.slug = d.slug
                WHERE datasets_fts MATCH ?
            """
            params: list[Any] = [query]
        else:
            sql = "SELECT * FROM datasets d WHERE 1=1"
            params = []

        if grup:
            sql += " AND d.grup = ?"
            params.append(grup)
        if opd:
            sql += " AND d.opd = ?"
            params.append(opd)
        if tahun:
            sql += " AND d.first_year <= ? AND d.last_year >= ?"
            params.extend([tahun, tahun])

        count_sql = f"SELECT COUNT(*) AS c FROM ({sql})"
        total = conn.execute(count_sql, params).fetchone()["c"]

        sql += " LIMIT ? OFFSET ?"
        params.extend([page_size, offset])
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    return {
        "results": rows,
        "page": page,
        "page_size": page_size,
        "total": total,
        "last_page": max(1, (total + page_size - 1) // page_size),
    }
