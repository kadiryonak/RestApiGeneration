from pathlib import Path

import pytest

from restgen.errors import MeasurementError
from restgen.evaluation.faults import (
    Verdict,
    crash_locations,
    fault_funnel,
    load_triage,
    normalise_error,
    write_triage_template,
)
from restgen.openapi import OpenApiSpec
from tests.support.traffic import interaction

SPEC = OpenApiSpec(
    {
        "openapi": "3.0.0",
        "paths": {
            "/bookings": {"post": {"responses": {}}},
            "/bookings/{id}": {"get": {"responses": {}}},
        },
    }
)


def _traffic() -> list:  # type: ignore[type-arg]
    return [
        interaction("POST", "/bookings", 500, "Internal Server Error id=17"),
        interaction("POST", "/bookings", 500, "Internal Server Error id=99"),  # same failure
        interaction("GET", "/bookings/1", 500, "KeyError: 'x'"),
        interaction("GET", "/nope", 503, "down"),
        interaction("POST", "/bookings", 201, "{}"),
    ]


def test_volatile_parts_are_normalised() -> None:
    assert normalise_error("id=17 at 0xdeadbeef") == normalise_error("id=99 at 0xcafe")


def test_funnel_deduplicates_and_waits_for_triage(tmp_path: Path) -> None:
    triage = tmp_path / "triage.toml"
    funnel = fault_funnel(SPEC, _traffic(), 500, triage)
    assert funnel.candidate_calls == 4
    assert len(funnel.unique_failures) == 3
    assert funnel.unique_failures[0].occurrences == 2
    assert funnel.unique_failures[2].operation == "UNMATCHED GET /nope"
    summary = funnel.summary()
    assert summary["triage_complete"] is False
    assert summary["verified_bugs"] is None

    write_triage_template(triage, funnel.unique_failures)
    write_triage_template(triage, funnel.unique_failures)  # idempotent
    text = triage.read_text()
    assert text.count("[failure.") == 3
    signatures = [f.signature for f in funnel.unique_failures]
    text = text.replace('verdict = "unreviewed"', 'verdict = "app_bug"', 2)
    text = text.replace('root_cause = ""', 'root_cause = "price-lookup"', 2)
    text = text.replace('verdict = "unreviewed"', 'verdict = "environment"')
    triage.write_text(text)

    reviewed = fault_funnel(SPEC, _traffic(), 500, triage)
    assert reviewed.verdicts[signatures[2]] is Verdict.ENVIRONMENT
    summary = reviewed.summary()
    assert summary["triage_complete"] is True
    assert summary["verified_bugs"] == 2
    assert summary["distinct_root_causes"] == 1


def test_app_bug_needs_root_cause(tmp_path: Path) -> None:
    triage = tmp_path / "triage.toml"
    triage.write_text('[failure.abc]\nverdict = "app_bug"\n')
    with pytest.raises(MeasurementError, match="root_cause"):
        load_triage(triage)
    triage.write_text('[failure.abc]\nverdict = "maybe"\n')
    with pytest.raises(MeasurementError):
        load_triage(triage)


def test_crash_locations_use_innermost_service_frame(tmp_path: Path) -> None:
    root = tmp_path / "svc"
    log = f'''INFO: started
Traceback (most recent call last):
  File "/usr/lib/python3.12/site-packages/starlette/routing.py", line 70, in app
    await func()
  File "{root}/app.py", line 40, in create_booking
    price = room_prices[booking.room_type]
KeyError: ''
INFO: 500 Internal Server Error
Traceback (most recent call last):
  File "{root}/app.py", line 40, in create_booking
KeyError: 'penthouse'
Traceback (most recent call last):
  File "/usr/lib/python3.12/site-packages/x.py", line 1, in f
RuntimeError: boom
'''
    assert crash_locations(log, root) == {
        "KeyError @ app.py:40": 2,
        "RuntimeError @ <outside service code>": 1,
    }


def test_failure_points_and_per_operation_counts(tmp_path: Path) -> None:
    from restgen.evaluation.faults import failure_points

    root = tmp_path / "svc"
    log = f'''Traceback (most recent call last):
  File "{root}/app.py", line 40, in create_booking
    price = room_prices[booking.room_type]
KeyError: 'x'
Traceback (most recent call last):
  File "{root}/app.py", line 12, in parse
  File "/usr/lib/python3.12/json/decoder.py", line 355, in raw_decode
json.decoder.JSONDecodeError: Expecting value
'''
    points, library = failure_points(log, root)
    assert points == {
        "create_booking @ app.py:40": 1,
        "raw_decode @ /usr/lib/python3.12/json/decoder.py:355": 1,
    }
    assert library == {"raw_decode @ /usr/lib/python3.12/json/decoder.py:355"}

    funnel = fault_funnel(SPEC, _traffic(), 500, tmp_path / "t.toml", log, root)
    summary = funnel.summary()
    assert summary["operations_with_500"] == 2  # POST /bookings, GET /bookings/{id}
    assert summary["operations_with_5xx"] == 3  # + the unmatched 503
    assert summary["unique_failure_points"] == 2
    assert summary["unique_library_failure_points"] == 1
