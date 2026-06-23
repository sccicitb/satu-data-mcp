from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import cache, catalog
from .api_client import SatuDataClient
from .config import INLINE_ROW_THRESHOLD, MCP_HTTP_HOST, MCP_HTTP_PORT, MCP_TRANSPORT
from .fileserver import start_fileserver, file_url
from .textutils import strip_html

mcp = FastMCP("satudata-garut", host=MCP_HTTP_HOST, port=MCP_HTTP_PORT)

_client = SatuDataClient()
_catalog_lock = asyncio.Lock()


async def _ensure_catalog_ready() -> None:
    start_fileserver()
    if catalog.row_count() > 0 and not catalog.is_stale():
        return
    async with _catalog_lock:
        if catalog.row_count() > 0 and not catalog.is_stale():
            return
        await catalog.refresh_catalog(_client)


def _summarize_row(row: dict[str, Any]) -> dict[str, Any]:
    desc = row.get("deskripsi") or ""
    excerpt = desc.split("\n")[0][:240]
    return {
        "slug": row["slug"],
        "judul": row["judul"],
        "kategori": row["grup"],
        "organisasi": row["opd"],
        "rentang_tahun": f"{row.get('first_year')}-{row.get('last_year')}",
        "jumlah_periode": row.get("total_data"),
        "total_views": row.get("total_views"),
        "total_download": row.get("total_download"),
        "ringkasan_deskripsi": excerpt,
    }


@mcp.tool()
async def search_datasets(
    query: str = "",
    grup: str = "",
    opd: str = "",
    tahun: int = 0,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    """Search the Satu Data Garut catalog (672 public government datasets).

    Searches a locally cached, periodically refreshed copy of the catalog so
    results return instantly without hitting the upstream API. Use the
    returned `kategori` and `organisasi` values as exact-match filters for
    `grup`/`opd` on subsequent calls - they come straight from the catalog,
    so they're guaranteed valid.

    Args:
        query: Free-text search across title and description (Indonesian).
        grup: Exact category name to filter by, e.g. "Kesehatan".
        opd: Exact government department name to filter by.
        tahun: Only include datasets whose year range covers this year.
        page: 1-based page number.
        page_size: Results per page.
    """
    await _ensure_catalog_ready()
    result = catalog.search_catalog(
        query=query or None,
        grup=grup or None,
        opd=opd or None,
        tahun=tahun or None,
        page=page,
        page_size=page_size,
    )
    return {
        "results": [_summarize_row(r) for r in result["results"]],
        "page": result["page"],
        "last_page": result["last_page"],
        "total": result["total"],
    }


@mcp.tool()
async def get_dataset_info(slug: str) -> dict[str, Any]:
    """Get full metadata for a dataset: column definitions, organization,
    category, time coverage, and summary statistics.

    Always call this before `get_dataset_data` - the `deskripsi` field
    documents what each data column means, which is required to interpret
    the rows correctly. Column meanings are not derivable from the data
    alone (e.g. coded fields like kode_kecamatan).

    Args:
        slug: Dataset slug as returned by `search_datasets`.
    """
    detail, ringkasan = await asyncio.gather(
        _client.get_dataset_detail(slug),
        _client.get_dataset_ringkasan(slug),
    )
    payload = detail.get("data") or {}
    dataset = payload.get("dataset") or {}
    return {
        "slug": slug,
        "judul": dataset.get("judul"),
        "deskripsi": strip_html(dataset.get("deskripsi")),
        "kategori": (payload.get("grup") or {}).get("name"),
        "organisasi": (payload.get("opd") or {}).get("name"),
        "periode_waktu": dataset.get("priode_waktu"),
        "rentang_tahun": f"{dataset.get('first_year')}-{dataset.get('last_year')}",
        "total_views": dataset.get("total_views"),
        "total_download": dataset.get("total_download"),
        "updated_at": dataset.get("updated_at"),
        "standar_data": payload.get("standar_data"),
        "ringkasan": ringkasan.get("data", ringkasan),
    }


@mcp.tool()
async def get_dataset_data(slug: str, format: str = "csv", force_refresh: bool = False) -> dict[str, Any]:
    """Fetch the actual data rows for a dataset.

    Small datasets (<= 500 rows) are returned inline as `rows`. Larger
    datasets are downloaded once, cached on disk, and served back as a
    `download_url` your sandbox/code-execution environment should fetch
    directly (e.g. `pandas.read_csv(download_url)`) - do not try to relay
    that response back through the chat context.

    Results are cached for up to 24h. This data updates on a weekly/monthly
    government reporting cycle, so a short-lived cache is safe by default;
    pass force_refresh=True if you specifically need the latest values
    right now (e.g. the user just mentioned a new release).

    Call `get_dataset_info` first to learn what each column means.

    Args:
        slug: Dataset slug as returned by `search_datasets`.
        format: "csv" or "json" - which cached file to point `download_url` at
            when the dataset is too large to inline. Ignored for small datasets.
        force_refresh: Bypass the cache and re-download from upstream.
    """
    if force_refresh or not cache.is_fresh(slug):
        payload = await _client.get_dataset_value(slug)
        rows = payload.get("data", [])
        last_update = payload.get("last_update")
        cache.write_cache(slug, rows, last_update)

    meta = cache.read_meta(slug)
    if meta is None:
        return {"slug": slug, "total_rows": 0, "columns": [], "rows": []}

    if meta["total_rows"] <= INLINE_ROW_THRESHOLD:
        rows = json.loads(cache.json_path(slug).read_text(encoding="utf-8"))
        return {
            "slug": slug,
            "total_rows": meta["total_rows"],
            "columns": meta["columns"],
            "last_update": meta["last_update"],
            "rows": rows,
        }

    start_fileserver()
    filename = f"{slug}.{format if format in ('csv', 'json') else 'csv'}"
    return {
        "slug": slug,
        "total_rows": meta["total_rows"],
        "columns": meta["columns"],
        "last_update": meta["last_update"],
        "download_url": file_url(filename),
        "note": "Dataset too large to inline - fetch download_url from your sandbox/code execution environment.",
    }


def main() -> None:
    mcp.run(transport=MCP_TRANSPORT)


if __name__ == "__main__":
    main()
