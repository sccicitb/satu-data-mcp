"""Verify the download_url path: force a low INLINE_ROW_THRESHOLD and confirm
the fileserver actually serves the cached file over HTTP."""
import asyncio
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import satudata_mcp.config as config
config.INLINE_ROW_THRESHOLD = 10  # force the "large dataset" branch

from satudata_mcp import server  # noqa: E402


async def main() -> None:
    slug = "jumlah-hotel-bintang-dan-non-bintang-di-kabupaten-garut-4463"
    data = await server.get_dataset_data(slug, format="csv")
    print("total_rows:", data["total_rows"])
    print("has download_url:", "download_url" in data)
    assert "download_url" in data, "expected download_url branch with low threshold"
    url = data["download_url"]
    print("download_url:", url)

    with urllib.request.urlopen(url, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    print("fetched bytes:", len(body))
    print("first line:", body.splitlines()[0])
    print("line count (incl header):", len(body.splitlines()))
    assert len(body.splitlines()) == data["total_rows"] + 1

    print("\nLarge-dataset download_url path verified end to end.")


if __name__ == "__main__":
    asyncio.run(main())
