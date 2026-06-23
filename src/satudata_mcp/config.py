import os
from pathlib import Path

API_BASE = "https://satudata-api.garutkab.go.id/api"

DATA_DIR = Path(os.environ.get("SATUDATA_MCP_HOME", Path.home() / ".cache" / "satudata-mcp"))
CACHE_DIR = DATA_DIR / "files"
CATALOG_DB_PATH = DATA_DIR / "catalog.sqlite3"

FILESERVER_HOST = os.environ.get("SATUDATA_MCP_FILESERVER_HOST", "127.0.0.1")
FILESERVER_PORT = int(os.environ.get("SATUDATA_MCP_FILESERVER_PORT", "8799"))

# MCP transport - "stdio" (default, for Command+Args style connectors) or
# "streamable-http" (for HTTP-based MCP connectors). Distinct from
# FILESERVER_*, which is always its own plain HTTP file server regardless
# of which transport the MCP protocol itself uses.
MCP_TRANSPORT = os.environ.get("SATUDATA_MCP_TRANSPORT", "stdio")
MCP_HTTP_HOST = os.environ.get("SATUDATA_MCP_HTTP_HOST", "127.0.0.1")
MCP_HTTP_PORT = int(os.environ.get("SATUDATA_MCP_HTTP_PORT", "8800"))

# Datasets with more rows than this are written to a cached file and served
# via URL instead of being inlined into the tool result.
INLINE_ROW_THRESHOLD = 500

CATALOG_REFRESH_INTERVAL_SECONDS = int(os.environ.get("SATUDATA_MCP_CATALOG_TTL", str(24 * 60 * 60)))
DATASET_VALUE_CACHE_TTL_SECONDS = int(os.environ.get("SATUDATA_MCP_VALUE_TTL", str(24 * 60 * 60)))

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
