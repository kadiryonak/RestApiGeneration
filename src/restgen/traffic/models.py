"""One recorded request/response pair and its JSONL (de)serialisation."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from restgen.errors import MeasurementError
from restgen.jsonio import read_jsonl

TRAFFIC_FILE = "traffic.jsonl"


@dataclass(frozen=True)
class HttpInteraction:
    sequence: int
    started_at: float  # unix time
    duration_ms: float
    method: str
    target: str  # path + query exactly as sent by the client
    request_headers: Mapping[str, str]
    request_body: str  # utf-8 text (lossy), truncated to the proxy's max_body_bytes
    request_body_size: int
    status: int | None  # None: the service did not answer (connection error / timeout)
    response_headers: Mapping[str, str]
    response_body: str
    response_body_size: int
    error: str | None = None

    @property
    def answered(self) -> bool:
        return self.status is not None

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> HttpInteraction:
        try:
            return cls(
                sequence=int(record["sequence"]),
                started_at=float(record["started_at"]),
                duration_ms=float(record["duration_ms"]),
                method=str(record["method"]),
                target=str(record["target"]),
                request_headers=dict(record["request_headers"]),
                request_body=str(record["request_body"]),
                request_body_size=int(record["request_body_size"]),
                status=None if record["status"] is None else int(record["status"]),
                response_headers=dict(record["response_headers"]),
                response_body=str(record["response_body"]),
                response_body_size=int(record["response_body_size"]),
                error=record.get("error"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MeasurementError(f"malformed traffic record: {exc}") from exc


def read_traffic(path: Path) -> Iterator[HttpInteraction]:
    if not path.is_file():
        raise MeasurementError(f"traffic file not found: {path}")
    for record in read_jsonl(path):
        yield HttpInteraction.from_record(record)
