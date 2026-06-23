"""Manual smoke test - exercises the tool logic without going through MCP transport."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from satudata_mcp import server  # noqa: E402


async def main() -> None:
    print("== search_datasets (cold catalog, triggers refresh) ==")
    res = await server.search_datasets(query="hotel", page=1, page_size=5)
    print(f"total={res['total']} last_page={res['last_page']}")
    for r in res["results"]:
        print(" -", r["slug"], "|", r["judul"])

    assert res["total"] > 0, "expected at least one hotel dataset"
    slug = next(r["slug"] for r in res["results"] if "hotel-bintang" in r["slug"])

    print("\n== search_datasets with grup filter ==")
    res2 = await server.search_datasets(grup="Kesehatan", page=1, page_size=3)
    print(f"total={res2['total']}")
    for r in res2["results"]:
        print(" -", r["slug"], "|", r["kategori"])

    print("\n== get_dataset_info ==")
    info = await server.get_dataset_info(slug)
    print("judul:", info["judul"])
    print("kategori/organisasi:", info["kategori"], "/", info["organisasi"])
    print("deskripsi (first 300 chars):")
    print(info["deskripsi"][:300])
    print("ringkasan keys:", list(info["ringkasan"].keys()) if isinstance(info["ringkasan"], dict) else type(info["ringkasan"]))

    print("\n== get_dataset_data (small dataset -> inline) ==")
    data = await server.get_dataset_data(slug)
    print("total_rows:", data["total_rows"], "columns:", data["columns"])
    print("has 'rows' inline:", "rows" in data, "has download_url:", "download_url" in data)
    if "rows" in data:
        print("first row:", data["rows"][0])

    print("\n== get_dataset_data again (should hit file cache, skip re-download) ==")
    data2 = await server.get_dataset_data(slug)
    print("total_rows:", data2["total_rows"])

    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
