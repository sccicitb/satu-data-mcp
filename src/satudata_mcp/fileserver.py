from __future__ import annotations

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from .config import CACHE_DIR, FILESERVER_HOST, FILESERVER_PORT, FILESERVER_PUBLIC_URL

_server: ThreadingHTTPServer | None = None
_thread: threading.Thread | None = None


def base_url() -> str:
    # When set, the public URL is what clients/sandboxes actually reach (e.g. a
    # reverse proxy doing TLS); FILESERVER_HOST/PORT are only the local bind.
    if FILESERVER_PUBLIC_URL:
        return FILESERVER_PUBLIC_URL.rstrip("/")
    return f"http://{FILESERVER_HOST}:{FILESERVER_PORT}"


def file_url(filename: str) -> str:
    return f"{base_url()}/{filename}"


def start_fileserver() -> str:
    """Serve CACHE_DIR over plain HTTP so sandboxed code can fetch large
    dataset files by URL instead of having them inlined into tool results.

    Logs go to stderr (BaseHTTPRequestHandler default), which is safe to
    use alongside an MCP stdio server since stdout is reserved for the
    protocol.
    """
    global _server, _thread
    if _server is not None:
        return base_url()

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(CACHE_DIR))
    _server = ThreadingHTTPServer((FILESERVER_HOST, FILESERVER_PORT), handler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    return base_url()
