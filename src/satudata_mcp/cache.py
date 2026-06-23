from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, DATASET_VALUE_CACHE_TTL_SECONDS


def _safe_name(slug: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in slug)


def json_path(slug: str) -> Path:
    return CACHE_DIR / f"{_safe_name(slug)}.json"


def csv_path(slug: str) -> Path:
    return CACHE_DIR / f"{_safe_name(slug)}.csv"


def meta_path(slug: str) -> Path:
    return CACHE_DIR / f"{_safe_name(slug)}.meta.json"


def read_meta(slug: str) -> dict[str, Any] | None:
    path = meta_path(slug)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_fresh(slug: str) -> bool:
    """TTL-based freshness check.

    The upstream detail endpoint's `updated_at` is not a reliable signal for
    whether the *data* changed - it gets bumped by unrelated writes (e.g.
    view-count increments) independent of the dataset-value endpoint's own
    `last_update`. Checking the real signal would require the same expensive
    call we're trying to avoid, so we fall back to a plain TTL instead:
    once fetched, a dataset's cached file is considered fresh for
    DATASET_VALUE_CACHE_TTL_SECONDS. Callers needing a guaranteed-current
    copy should pass force_refresh=True at the tool layer.
    """
    meta = read_meta(slug)
    if meta is None:
        return False
    if not json_path(slug).exists() or not csv_path(slug).exists():
        return False
    fetched_at = meta.get("fetched_at")
    if fetched_at is None:
        return False
    return (time.time() - fetched_at) < DATASET_VALUE_CACHE_TTL_SECONDS


def write_cache(slug: str, rows: list[dict[str, Any]], last_update: str | None) -> dict[str, Any]:
    columns = list(rows[0].keys()) if rows else []

    json_path(slug).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    with csv_path(slug).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    meta = {
        "slug": slug,
        "last_update": last_update,
        "fetched_at": time.time(),
        "total_rows": len(rows),
        "columns": columns,
    }
    meta_path(slug).write_text(json.dumps(meta), encoding="utf-8")
    return meta
