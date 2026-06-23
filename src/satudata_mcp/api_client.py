from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .config import API_BASE

_TIMEOUT = httpx.Timeout(30.0)
_MAX_RETRIES = 5


class SatuDataClient:
    """Thin wrapper around the public satudata-api.garutkab.go.id REST API.

    No authentication is required - all endpoints used here are public.
    The API rate-limits bursts of requests (observed 429 after ~50 rapid
    sequential calls), so every request goes through `_get`, which retries
    with backoff honoring `Retry-After` when present.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=API_BASE, timeout=_TIMEOUT)
        self.request_count = 0  # exposed for cache-hit testing, not used in normal operation

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        delay = 1.0
        for attempt in range(_MAX_RETRIES):
            self.request_count += 1
            resp = await self._client.get(path, params=params)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay
                await asyncio.sleep(wait)
                delay = min(delay * 2, 30.0)
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    async def list_datasets(
        self,
        page: int = 1,
        search: str | None = None,
        grup: str | None = None,
        opd: str | None = None,
        tahun: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page}
        if search:
            params["search"] = search
        if grup:
            params["grup"] = grup
        if opd:
            params["opd"] = opd
        if tahun:
            params["tahun"] = tahun
        return await self._get("/datasets", params=params)

    async def get_dataset_detail(self, slug: str) -> dict[str, Any]:
        return await self._get(f"/datasets/{slug}", params={"page": 1})

    async def get_dataset_ringkasan(self, slug: str) -> dict[str, Any]:
        return await self._get(f"/datasets/{slug}/ringkasan")

    async def get_dataset_value(self, slug: str) -> dict[str, Any]:
        """Fetch the full, unpaginated row set for a dataset.

        Response shape: {"success": bool, "last_update": str, "data": [ {...row}, ... ]}
        """
        return await self._get(f"/dataset-value/{slug}")
