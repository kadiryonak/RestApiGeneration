"""6. Hypothesis against a real HTTP API, driven by its OpenAPI document.

This is a hand-written miniature of restgen's Hypothesis baseline
(src/restgen/baselines/hypothesis_pytest.py), which writes such tests automatically:

1. start the service on a real port,
2. read its OpenAPI document,
3. turn each operation's JSON Schemas into strategies (hypothesis-jsonschema),
4. send generated requests; the oracle is "never a 5xx".

Run:  example/.venv/bin/pytest example/hypothesis/test_06_rest_api.py -v
Two tests FAIL on purpose: they find the two bugs in booking_api.py. One operation is
never reached successfully: GET /bookings/{id} needs an id that a POST created first,
which independent random requests rarely provide (test_04 shows how sequences help).
"""

import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import uvicorn
from booking_api import app
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis_jsonschema import from_schema


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    """Run the API on a real port for the whole module (like a deployed service)."""
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()


# The OpenAPI document is what a black-box tool gets: here straight from FastAPI.
SPEC = app.openapi()
COMPONENTS = SPEC.get("components", {}).get("schemas", {})


def body_schema(path: str, method: str) -> dict[str, Any]:
    """Request body schema with its $ref inlined (hypothesis-jsonschema needs plain JSON
    Schema; restgen's openapi.py does this generally)."""
    ref = SPEC["paths"][path][method]["requestBody"]["content"]["application/json"]["schema"]
    return COMPONENTS[ref["$ref"].rsplit("/", 1)[-1]]


def param_schema(path: str, method: str, name: str) -> dict[str, Any]:
    for param in SPEC["paths"][path][method].get("parameters", []):
        if param["name"] == name:
            schema: dict[str, Any] = param["schema"]
            return schema
    raise KeyError(name)


API_SETTINGS = settings(
    max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)


@API_SETTINGS
@given(body=from_schema(body_schema("/bookings", "post")))
def test_post_bookings_never_5xx(base_url: str, body: dict[str, Any]) -> None:
    response = httpx.post(f"{base_url}/bookings", json=body)
    # FAILS: almost every random room_type is unknown -> KeyError -> 500 (bug 1)
    assert response.status_code < 500, f"{response.status_code} for {body}"


@API_SETTINGS
@given(days=from_schema(param_schema("/stats", "get", "days")))
def test_get_stats_never_5xx(base_url: str, days: int) -> None:
    response = httpx.get(f"{base_url}/stats", params={"days": days})
    # FAILS: shrinks to days=0 -> ZeroDivisionError -> 500 (bug 2)
    assert response.status_code < 500, f"{response.status_code} for days={days}"


@API_SETTINGS
@given(booking_id=st.integers(min_value=-10, max_value=10**6))
def test_get_booking_never_5xx(base_url: str, booking_id: int) -> None:
    response = httpx.get(f"{base_url}/bookings/{booking_id}")
    # passes: unknown ids correctly give 404, but no request ever gets a 200 here,
    # because no valid booking exists (the POST above always crashes)
    assert response.status_code < 500
