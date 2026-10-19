"""A tiny in-process HTTP service used as the upstream of the recording proxy in tests."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class _EchoHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __getattr__(self, name: str) -> Any:
        if name.startswith("do_"):
            return self._answer
        raise AttributeError(name)

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if self.path.startswith("/boom"):
            status, payload = 500, b"Internal Server Error"
        else:
            status = 201 if self.command == "POST" else 200
            payload = json.dumps(
                {
                    "method": self.command,
                    "path": self.path,
                    "body": body.decode(),
                    "authorization": self.headers.get("Authorization"),
                }
            ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@contextmanager
def echo_service() -> Iterator[str]:
    """Serve the echo handler on a free port; yields its base URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host!s}:{port}"
    finally:
        server.shutdown()
        server.server_close()
