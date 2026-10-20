import pytest

from restgen.evaluation.operations import SuccessCriterion
from restgen.evaluation.timeline import timeline
from restgen.openapi import OpenApiSpec
from tests.support.traffic import interaction

SPEC = OpenApiSpec(
    {
        "openapi": "3.0.0",
        "paths": {
            "/a": {"get": {"responses": {}}, "post": {"responses": {}}},
            "/a/{id}": {"get": {"responses": {}}},
            "/b": {"get": {"responses": {}}},
        },
    }
)


def _at(seconds: float, method: str, target: str, status: int | None, body: str = ""):  # type: ignore[no-untyped-def]
    item = interaction(method, target, status, body)
    return type(item)(**{**item.to_record(), "started_at": 1000.0 + seconds})


def test_first_times_curves_and_auc() -> None:
    traffic = [
        _at(1, "GET", "/a", 200),
        _at(2, "POST", "/a", 400),
        _at(4, "POST", "/a", 201),
        _at(5, "GET", "/a/1", 500, "boom 1"),
        _at(6, "GET", "/a/2", 500, "boom 2"),  # same failure after normalisation
        _at(8, "GET", "/a/3", 200),
    ]
    line = timeline(SPEC, traffic, SuccessCriterion(), 500, origin=1000.0, budget_seconds=10.0)
    summary = line.summary()
    assert summary["first_success"] == {"GET /a": 1.0, "POST /a": 4.0, "GET /a/{id}": 8.0}
    assert summary["time_to_first_failure"] == 5.0
    assert summary["failure_curve"] == [[5.0, 1]]
    assert summary["attempted_curve"] == [[1.0, 1], [2.0, 2], [5.0, 3]]
    # (9 + 6 + 2) seconds of success out of 4 operations x 10 s
    assert summary["success_coverage_auc"] == pytest.approx(17 / 40)
    assert summary["time_to_last_new_success"] == 8.0
    assert summary["requests"] == 6
    assert summary["success_curve_by_request"] == [[1, 1], [3, 2], [6, 3]]


def test_defaults_without_traffic_or_origin() -> None:
    line = timeline(SPEC, [], SuccessCriterion(), 500, origin=None, budget_seconds=10.0)
    assert line.summary()["time_to_first_failure"] is None
    assert line.area_under_success() == 0.0
    assert timeline(SPEC, [], SuccessCriterion(), 500, None, 0).area_under_success() is None
