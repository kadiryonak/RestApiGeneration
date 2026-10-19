"""Builders for recorded interactions in tests."""

from __future__ import annotations

from restgen.traffic.models import HttpInteraction


def interaction(
    method: str, target: str, status: int | None, body: str = "", sequence: int = 1
) -> HttpInteraction:
    return HttpInteraction(
        sequence=sequence,
        started_at=0.0,
        duration_ms=1.0,
        method=method,
        target=target,
        request_headers={},
        request_body="",
        request_body_size=0,
        status=status,
        response_headers={},
        response_body=body,
        response_body_size=len(body),
        error=None if status is not None else "ConnectError",
    )
