"""Local development server for the built site (standard library only)."""

from __future__ import annotations

import functools
import http.server
import os
import socketserver
import threading
import webbrowser
from pathlib import Path
from typing import Optional


class Handler(http.server.SimpleHTTPRequestHandler):
    """Quiet handler with no-cache headers so refreshes show new data."""

    def end_headers(self) -> None:  # pragma: no cover - thin wrapper
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # pragma: no cover
        if os.environ.get("AIINDEX_VERBOSE"):
            super().log_message(fmt, *args)


def serve(directory: Path, port: int = 8000, host: str = "127.0.0.1", open_browser: bool = False) -> None:
    directory = Path(directory).resolve()
    handler = functools.partial(Handler, directory=str(directory))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((host, port), handler) as httpd:
        url = "http://%s:%d/" % ("127.0.0.1" if host in ("0.0.0.0", "") else host, port)
        print("serving %s at %s" % (directory, url))
        if open_browser:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
