"""A recording reverse proxy.

Every tool talks to the service through this proxy, so operation coverage, status codes,
failures and request counts are measured identically for every tool, independent of
whatever the tool itself reports. Records go to a JSON Lines file, one per exchange.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import TracebackType
from typing import Any, ClassVar

import httpx

from restgen.config import ProxySettings
from restgen.jsonio import append_jsonl
from restgen.traffic.models import HttpInteraction

# RFC 9110 §7.6.1 connection-specific headers, never forwarded.
HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)
REDACTED = "[redacted]"


class RecordingProxy:
    """Forward ``http://127.0.0.1:<port>`` to ``upstream`` and record every exchange.

    Use as a context manager; ``url`` is the address to hand to the tool.
    """

    def __init__(
        self,
        upstream: str,
        log_path: Path,
        settings: ProxySettings,
        timeout_seconds: float,
        port: int = 0,
    ) -> None:
        self.upstream = upstream.rstrip("/")
        self.log_path = log_path
        self._settings = settings
        self._client = httpx.Client(timeout=timeout_seconds, follow_redirects=False)
        self._lock = threading.Lock()
        self._sequence = 0
        self._server = ThreadingHTTPServer(("127.0.0.1", port), _handler_for(self))
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    @property
    def request_count(self) -> int:
        with self._lock:
            return self._sequence

    def start(self) -> RecordingProxy:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")  # one proxy session = one log
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)
        self._client.close()

    def __enter__(self) -> RecordingProxy:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    # -- called from handler threads -------------------------------------------------

    def forward(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        started = time.time()
        clock = time.perf_counter()
        forwarded = {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}
        status: int | None = None
        response_headers: list[tuple[str, str]] = []
        content = b""
        error: str | None = None
        try:
            response = self._client.request(
                method, self.upstream + target, headers=forwarded, content=body
            )
            status = response.status_code
            content = response.content
            response_headers = [
                (k, v) for k, v in response.headers.multi_items() if k.lower() not in HOP_BY_HOP
            ]
            # httpx already decoded the body; the client must not decode it again.
            response_headers = [
                (k, v) for k, v in response_headers if k.lower() != "content-encoding"
            ]
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"
        duration_ms = (time.perf_counter() - clock) * 1000
        self._record(
            method,
            target,
            headers,
            body,
            status,
            response_headers,
            content,
            error,
            started,
            duration_ms,
        )
        if status is None:
            return 502, [("Content-Type", "text/plain")], b"restgen proxy: upstream unreachable"
        return status, response_headers, content

    def _record(
        self,
        method: str,
        target: str,
        request_headers: dict[str, str],
        request_body: bytes,
        status: int | None,
        response_headers: list[tuple[str, str]],
        response_body: bytes,
        error: str | None,
        started: float,
        duration_ms: float,
    ) -> None:
        limit = self._settings.max_body_bytes
        with self._lock:
            self._sequence += 1
            interaction = HttpInteraction(
                sequence=self._sequence,
                started_at=started,
                duration_ms=round(duration_ms, 3),
                method=method,
                target=target,
                request_headers=self._redact(request_headers.items()),
                request_body=request_body[:limit].decode("utf-8", "replace"),
                request_body_size=len(request_body),
                status=status,
                response_headers=self._redact(response_headers),
                response_body=response_body[:limit].decode("utf-8", "replace"),
                response_body_size=len(response_body),
                error=error,
            )
            append_jsonl(self.log_path, interaction.to_record())

    def _redact(self, items: Any) -> dict[str, str]:
        redacted = self._settings.redact_headers
        return {
            str(k).lower(): (REDACTED if str(k).lower() in redacted else str(v)) for k, v in items
        }


def _handler_for(proxy: RecordingProxy) -> type[BaseHTTPRequestHandler]:
    class Handler(_ProxyHandler):
        owner: ClassVar[RecordingProxy] = proxy

    return Handler


class _ProxyHandler(BaseHTTPRequestHandler):
    owner: ClassVar[RecordingProxy]
    protocol_version = "HTTP/1.1"

    def __getattr__(self, name: str) -> Any:
        # Tools send arbitrary verbs (TRACE, QUERY, ...): route every do_<VERB> to _forward.
        if name.startswith("do_"):
            return self._forward
        raise AttributeError(name)

    def _forward(self) -> None:
        body = self._read_body()
        status, headers, content = self.owner.forward(
            self.command, self.path, dict(self.headers.items()), body
        )
        self.send_response(status)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)

    def _read_body(self) -> bytes:
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            chunks: list[bytes] = []
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    self.rfile.readline()
                    return b"".join(chunks)
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def log_message(self, format: str, *args: Any) -> None:
        """Silence the default stderr access log; traffic.jsonl is the log."""
