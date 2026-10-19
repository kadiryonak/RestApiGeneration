from restgen.coverage.models import CodeCoverage
from restgen.evaluation.operations import SuccessCriterion, operation_coverage, status_class
from restgen.evaluation.retention import CoverageRetention, retention
from restgen.openapi import OpenApiSpec
from tests.support.traffic import interaction

SPEC = OpenApiSpec(
    {
        "openapi": "3.0.0",
        "paths": {
            "/items": {"get": {"responses": {}}, "post": {"responses": {}}},
            "/items/{id}": {"get": {"responses": {}}, "delete": {"responses": {}}},
        },
    }
)


def test_attempt_and_success_coverage_are_separate() -> None:
    traffic = [
        interaction("GET", "/openapi.json", 200),  # schema download: unmatched
        interaction("POST", "/items", 400),  # attempted, not successful
        interaction("POST", "/items", 422),
        interaction("GET", "/items/7", 404),
        interaction("GET", "/items/8", 200),
        interaction("PATCH", "/items/8", 405),  # undocumented method: unmatched
        interaction("GET", "/items", None),  # no answer: attempted, not successful
    ]
    coverage = operation_coverage(SPEC, traffic, SuccessCriterion())
    assert coverage.attempted == {"POST /items", "GET /items/{id}", "GET /items"}
    assert coverage.succeeded == {"GET /items/{id}"}
    assert coverage.attempt_ratio == 0.75
    assert coverage.success_ratio == 0.25
    assert coverage.unmatched_requests == 2
    assert coverage.unanswered_requests == 1
    summary = coverage.summary()
    assert summary["never_attempted"] == ["DELETE /items/{id}"]
    assert summary["status_classes"]["POST /items"] == {"4xx": 2}
    assert summary["status_classes"]["GET /items"] == {"none": 1}


def test_excluded_operations_leave_the_scope() -> None:
    traffic = [interaction("DELETE", "/items/1", 204)]
    coverage = operation_coverage(
        SPEC, traffic, SuccessCriterion(), excluded=["DELETE /items/{id}"]
    )
    assert len(coverage.in_scope) == 3
    assert coverage.attempted == set()


def test_custom_success_range_and_status_class() -> None:
    success = SuccessCriterion(200, 399)
    assert success(302)
    assert not success(None)
    assert status_class(503) == "5xx"


def test_retention() -> None:
    assert retention({"a", "b", "c", "d"}, {"a", "b", "x"}) == 0.5
    assert retention(set(), {"a"}) is None
    exploration = CodeCoverage("t", frozenset({"f:1", "f:2"}), 4, frozenset({"f:1->2"}), 2)
    output = CodeCoverage("t", frozenset({"f:1", "f:3"}), 4, frozenset(), 2)
    result = CoverageRetention(exploration, output)
    assert result.line_retention == 0.5
    assert result.branch_retention == 0.0
    assert result.summary()["lines_only_in_output"] == 1
