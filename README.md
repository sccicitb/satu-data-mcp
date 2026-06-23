# satudata-mcp

An MCP server giving an agentic LLM app search/get/analyse access to
[Satu Data Garut](https://satudata.garutkab.go.id/datasets/) — the Garut
Regency (Indonesia) open government data portal, ~672 public datasets.

It talks to the portal's underlying REST API directly
(`satudata-api.garutkab.go.id`) rather than scraping HTML — no
authentication required, everything used here is public.

## Tools

### `search_datasets(query, grup, opd, tahun, page, page_size)`
Full-text search over a **locally cached copy** of the catalog (SQLite +
FTS5). Instant, no network call once warm. `grup` (category) and `opd`
(department) are exact-match filters — use the `kategori`/`organisasi`
values returned by a prior search, since those come straight from the
catalog and are guaranteed valid.

### `get_dataset_info(slug)`
Full metadata for one dataset: HTML-stripped description (which documents
what each data column means — required, since coded fields like
`kode_kecamatan` aren't self-explanatory), organization, category, time
coverage, and summary statistics (`ringkasan`).

### `get_dataset_data(slug, format="csv", force_refresh=False)`
The actual data rows.
- **≤ 500 rows** → returned inline as `rows` in the tool result.
- **> 500 rows** → downloaded once, cached to disk, served back as a
  `download_url`. Your sandbox/code-execution environment should fetch
  that URL directly (`pandas.read_csv(download_url)`) — never try to
  relay a multi-MB payload back through the chat context.

## Architecture

```
satudata-api.garutkab.go.id
        │
        ▼
  api_client.py   (httpx, retry+backoff on 429)
        │
   ┌────┴─────┐
   ▼          ▼
catalog.py   cache.py   (SQLite FTS5)   (file cache: json+csv+meta per slug)
   │              │
   ▼              ▼
search_datasets  get_dataset_data ──▶ fileserver.py (ThreadingHTTPServer)
                                              │
                                              ▼
                                    sandbox fetches download_url directly
```

The MCP server never tries to push large payloads through the MCP
transport. For big datasets it just writes a cache file and hands back a
plain HTTP URL — any sandbox with outbound network access (local
subprocess, E2B, Daytona, etc.) can fetch it itself, at zero token cost.

## Caching model

| Layer | Mechanism | TTL |
|---|---|---|
| Catalog (titles, descriptions, filters) | SQLite FTS5, full rebuild on refresh | 24h (`SATUDATA_MCP_CATALOG_TTL`) |
| Dataset rows (`dataset-value`) | File cache (json+csv) per slug | 24h (`SATUDATA_MCP_VALUE_TTL`) |

**Why TTL and not change-detection:** the upstream detail endpoint's
`updated_at` field is *not* a reliable signal for whether the underlying
data changed — it gets bumped by unrelated writes (e.g. view-count
increments) independent of the data itself. Checking the real signal
(`dataset-value`'s own `last_update`) requires the same expensive call
we're trying to avoid by caching. Given the data updates on a
weekly/monthly government reporting cycle, a 24h TTL is a safe default.
Pass `force_refresh=True` on `get_dataset_data` when you need a
guaranteed-current copy right now.

## Install & run

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m satudata_mcp
```

Runs over stdio. Add to an MCP client config like:

```json
{
  "mcpServers": {
    "satudata-garut": {
      "command": "C:/path/to/.venv/Scripts/python.exe",
      "args": ["-m", "satudata_mcp"]
    }
  }
}
```

## Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `SATUDATA_MCP_HOME` | `~/.cache/satudata-mcp` | Catalog DB + file cache location |
| `SATUDATA_MCP_FILESERVER_HOST` | `127.0.0.1` | Host the file server binds to |
| `SATUDATA_MCP_FILESERVER_PORT` | `8799` | Port the file server binds to |
| `SATUDATA_MCP_CATALOG_TTL` | `86400` (24h) | Catalog refresh interval, seconds |
| `SATUDATA_MCP_VALUE_TTL` | `86400` (24h) | Dataset-value cache TTL, seconds |

If your sandbox is *not* on the same host/network as the MCP server,
set `SATUDATA_MCP_FILESERVER_HOST` to an interface reachable from the
sandbox (and make sure the port is open to it) — the `download_url`
returned by `get_dataset_data` is built from these two values.

## Known upstream quirks

- **Rate limiting**: the API returns `429` after ~50 rapid sequential
  requests. `api_client.py` retries with backoff (honoring `Retry-After`),
  and the catalog refresh throttles itself at ~5 req/s.
- **`dataset-value` on a bad slug returns `500`, not `404`** (the
  `/datasets/{slug}` detail endpoint does 404 correctly, but the bulk data
  endpoint doesn't validate the slug the same way). Either way the tool
  raises — callers should expect an exception for invalid slugs from
  either endpoint, not assume a specific status code.
- **Some numeric columns contain the literal string `"-"`** instead of
  `0` or `null` for missing values (seen in real data, e.g. hotel counts).
  This is passed through as-is — handle it when doing numeric analysis
  in the sandbox (e.g. `pd.to_numeric(col, errors="coerce")`).
- **`sort=` query param** on the listing endpoint had no observable effect
  in testing (`terpopuler` returned the same order as default). Not relied
  on by the catalog refresh (which always rebuilds from default order).

## Tests

```
scripts/smoke_test.py             search → info → data (small, inline), basic cache hit
scripts/smoke_test_large.py       forces the download_url branch, verifies fileserver delivery
scripts/smoke_test_edge_cases.py  404s, empty results, pagination overflow, mixed-type columns,
                                   concurrent catalog refresh, a real ~29k-row/6MB dataset end to
                                   end, cache-hit verified by request count (not just timing),
                                   force_refresh, malformed-row CSV writer behavior
```

Run any of them with `.venv/Scripts/python.exe scripts/<name>.py`.
