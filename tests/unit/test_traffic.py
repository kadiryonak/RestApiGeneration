import json
import socket
from pathlib import Path

import httpx
import pytest

from restgen.config import ProxySettings
from restgen.errors import MeasurementError
from restgen.traffic.models import HttpInteraction, read_traffic
from restgen.traffic.proxy import REDACTED, RecordingProxy
from tests.support.upstream import echo_service

SETTINGS = ProxySettings(max_body_bytes=8, redact_headers=("authorization",))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def test_proxy_forwards_and_records_every_exchange(tmp_path: Path) -> None:
    log = tmp_path / "traffic.jsonl"
    with echo_service() as upstream, RecordingProxy(upstream, log, SETTINGS, 5.0) as proxy:
        get = httpx.get(f"{proxy.url}/users/1?verbose=true", headers={"Authorization": "secret"})
        post = httpx.post(f"{proxy.url}/users", content=b'{"name": "Ada Lovelace"}')
        boom = httpx.request("TRACE", f"{proxy.url}/boom")
        assert proxy.request_count == 3

    assert get.status_code == 200
    assert get.json()["authorization"] == "secret"  # forwarded unchanged
    assert get.json()["path"] == "/users/1?verbose=true"
    assert post.status_code == 201
    assert json.loads(post.json()["body"]) == {"name": "Ada Lovelace"}
    assert boom.status_code == 500

    records = list(read_traffic(log))
    assert [r.sequence for r in records] == [1, 2, 3]
    assert [(r.method, r.target, r.status) for r in records] == [
        ("GET", "/users/1?verbose=true", 200),
        ("POST", "/users", 201),
        ("TRACE", "/boom", 500),
    ]
    assert records[0].request_headers["authorization"] == REDACTED
    assert records[1].request_body == '{"name":'  # truncated to max_body_bytes
    assert records[1].request_body_size == len(b'{"name": "Ada Lovelace"}')
    assert all(r.duration_ms >= 0 and r.answered for r in records)


def test_unreachable_upstream_is_recorded_as_unanswered(tmp_path: Path) -> None:
    log = tmp_path / "traffic.jsonl"
    upstream = f"http://127.0.0.1:{_free_port()}"
    with RecordingProxy(upstream, log, SETTINGS, 2.0) as proxy:
        response = httpx.get(f"{proxy.url}/anything")
    assert response.status_code == 502
    (record,) = read_traffic(log)
    assert record.status is None
    assert not record.answered
    assert record.error is not None


def test_record_round_trip_and_malformed_record() -> None:
    interaction = HttpInteraction(
        sequence=1,
        started_at=0.0,
        duration_ms=1.5,
        method="GET",
        target="/x",
        request_headers={},
        request_body="",
        request_body_size=0,
        status=204,
        response_headers={},
        response_body="",
        response_body_size=0,
    )
    assert HttpInteraction.from_record(interaction.to_record()) == interaction
    with pytest.raises(MeasurementError):
        HttpInteraction.from_record({"sequence": 1})


def test_missing_traffic_file(tmp_path: Path) -> None:
    with pytest.raises(MeasurementError):
        list(read_traffic(tmp_path / "nope.jsonl"))
