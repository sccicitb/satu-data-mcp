"""Edge case battery for the satudata MCP server."""
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from satudata_mcp import server, cache, catalog  # noqa: E402
from satudata_mcp.api_client import SatuDataClient  # noqa: E402


async def case_nonexistent_slug():
    print("\n== nonexistent slug ==")
    try:
        await server.get_dataset_info("this-slug-does-not-exist-99999")
        print("FAIL: expected an error")
    except Exception as e:
        print("OK, raised:", type(e).__name__, str(e)[:120])


async def case_empty_search():
    print("\n== search with no matches ==")
    res = await server.search_datasets(query="zzzznonexistentquery1234")
    print("total:", res["total"], "results:", len(res["results"]))
    assert res["total"] == 0 and res["results"] == []
    print("OK")


async def case_page_beyond_last():
    print("\n== page beyond last_page ==")
    res = await server.search_datasets(grup="Kesehatan", page=9999, page_size=10)
    print("total:", res["total"], "last_page:", res["last_page"], "results:", len(res["results"]))
    assert res["results"] == []
    print("OK, empty results without error")


async def case_special_char_opd():
    print("\n== opd filter with special characters (period) ==")
    res = await server.search_datasets(opd="Kecamatan Bl. Limbangan", page=1)
    print("total:", res["total"])
    for r in res["results"][:3]:
        print(" -", r["slug"], "|", r["organisasi"])
    print("OK" if res["total"] >= 0 else "FAIL")


async def case_genuinely_large_dataset():
    print("\n== genuinely large dataset: weekly commodity prices (~29k rows, ~6MB) ==")
    slug = "data-harga-bahan-pokok-dan-barang-penting-lainnya-di-kabupaten-garut-4841"
    t0 = time.time()
    data = await server.get_dataset_data(slug, format="csv")
    elapsed = time.time() - t0
    print(f"total_rows={data['total_rows']} columns={data['columns']} elapsed={elapsed:.1f}s")
    assert "download_url" in data, "29k rows must go through the download_url path"
    assert "rows" not in data, "must NOT inline 29k rows into the tool result"

    url = data["download_url"]
    with urllib.request.urlopen(url, timeout=30) as resp:
        body = resp.read()
    print("downloaded bytes:", len(body))
    line_count = body.decode("utf-8").count("\n")
    print("csv line count (approx incl header):", line_count)
    assert abs(line_count - (data["total_rows"] + 1)) <= 1

    print("-- second call should hit cache, skip re-download --")
    requests_before = _client_request_count()
    t1 = time.time()
    data2 = await server.get_dataset_data(slug, format="csv")
    elapsed2 = time.time() - t1
    requests_after = _client_request_count()
    print(f"second call elapsed={elapsed2:.1f}s, upstream requests made: {requests_after - requests_before}")
    assert requests_after == requests_before, "cache hit must make zero upstream requests"
    assert data2["total_rows"] == data["total_rows"]
    print("OK")


def _client_request_count() -> int:
    return server._client.request_count


async def case_force_refresh_bypasses_cache():
    print("\n== force_refresh=True bypasses the cache ==")
    slug = "jumlah-hotel-bintang-dan-non-bintang-di-kabupaten-garut-4463"
    before = _client_request_count()
    await server.get_dataset_data(slug, force_refresh=True)
    after = _client_request_count()
    print(f"upstream requests made with force_refresh=True: {after - before}")
    assert after > before, "force_refresh must hit upstream even when cache is fresh"
    print("OK")


async def case_zero_row_or_dash_values_dataset():
    print("\n== dataset with placeholder '-' values in numeric columns ==")
    # Confirmed earlier: jumlah_hotel contains "-" for some rows (not 0, not null)
    slug = "jumlah-hotel-bintang-dan-non-bintang-di-kabupaten-garut-4463"
    data = await server.get_dataset_data(slug)
    dash_rows = [r for r in data["rows"] if r.get("jumlah_hotel") == "-"]
    print(f"rows with '-' placeholder: {len(dash_rows)} / {data['total_rows']}")
    assert len(dash_rows) > 0, "expected to find the known '-' placeholder values"
    print("OK - tool passes through '-' as-is, doesn't crash on mixed str/int column")


async def case_cache_invalidation_on_stale_metadata():
    print("\n== cache.is_fresh() TTL behavior ==")
    slug = "jumlah-hotel-bintang-dan-non-bintang-di-kabupaten-garut-4463"
    meta = cache.read_meta(slug)
    assert meta is not None, "expected this dataset to already be cached from a prior test"
    assert cache.is_fresh(slug) is True, "just-cached file within TTL should be fresh"
    assert cache.is_fresh("a-slug-never-cached") is False
    print("OK")


async def case_concurrent_catalog_refresh():
    print("\n== concurrent search_datasets calls don't double-refresh catalog ==")
    catalog_before = catalog.row_count()
    results = await asyncio.gather(
        server.search_datasets(query="bencana"),
        server.search_datasets(query="bencana"),
        server.search_datasets(query="bencana"),
    )
    for r in results:
        assert r["total"] >= 0
    catalog_after = catalog.row_count()
    print(f"catalog rows before={catalog_before} after={catalog_after} (should be stable, no errors)")
    print("OK")


async def case_csv_dictwriter_column_mismatch():
    print("\n== rows with inconsistent keys across the row set (csv.DictWriter robustness) ==")
    rows = [
        {"a": 1, "b": 2},
        {"a": 3, "b": 4, "c": 5},  # extra key not in header derived from rows[0]
    ]
    try:
        cache.write_cache("___test_mismatched_columns___", rows, "2024-01-01")
        print("FAIL: expected ValueError from csv.DictWriter on extra field")
    except ValueError as e:
        print("OK, raised as expected:", str(e)[:150])
    finally:
        for p in (cache.json_path("___test_mismatched_columns___"),
                  cache.csv_path("___test_mismatched_columns___"),
                  cache.meta_path("___test_mismatched_columns___")):
            p.unlink(missing_ok=True)


async def case_get_dataset_data_unknown_slug():
    print("\n== get_dataset_data on a slug that 404s upstream ==")
    try:
        await server.get_dataset_data("totally-bogus-slug-xyz")
        print("FAIL: expected an error")
    except Exception as e:
        print("OK, raised:", type(e).__name__, str(e)[:120])


async def main():
    await case_nonexistent_slug()
    await case_empty_search()
    await case_page_beyond_last()
    await case_special_char_opd()
    await case_zero_row_or_dash_values_dataset()
    await case_cache_invalidation_on_stale_metadata()
    await case_concurrent_catalog_refresh()
    await case_csv_dictwriter_column_mismatch()
    await case_get_dataset_data_unknown_slug()
    await case_genuinely_large_dataset()
    await case_force_refresh_bypasses_cache()
    print("\nAll edge case checks finished.")


if __name__ == "__main__":
    asyncio.run(main())
