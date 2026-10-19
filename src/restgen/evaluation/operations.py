"""API operation coverage (analysis §5.2), measured from the proxy's traffic recording.

* C_attempt = operations called at least once / operations in scope
* C_success = operations with at least one *successful* response / operations in scope

"Successful" is the configured status range (default 2xx). A 400 for a malformed body is
an attempt, not a success: rejecting garbage is not the same as creating and reading a
resource. Requests that match no documented operation (schema download, probes for
undocumented methods) are counted separately and never inflate coverage.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from restgen.coverage.models import ratio
from restgen.openapi import OpenApiSpec
from restgen.traffic.models import HttpInteraction


@dataclass(frozen=True)
class SuccessCriterion:
    min_status: int = 200
    max_status: int = 299

    def __call__(self, status: int | None) -> bool:
        return status is not None and self.min_status <= status <= self.max_status


@dataclass(frozen=True)
class OperationCoverage:
    in_scope: frozenset[str]
    attempted: frozenset[str]
    succeeded: frozenset[str]
    status_classes: Mapping[str, Mapping[str, int]]  # operation -> {"2xx": n, ...}
    requests: int
    matched_requests: int
    unanswered_requests: int  # connection errors / timeouts at the proxy

    @property
    def attempt_ratio(self) -> float | None:
        return ratio(len(self.attempted), len(self.in_scope))

    @property
    def success_ratio(self) -> float | None:
        return ratio(len(self.succeeded), len(self.in_scope))

    @property
    def unmatched_requests(self) -> int:
        return self.requests - self.matched_requests

    def summary(self) -> dict[str, Any]:
        return {
            "operations_in_scope": len(self.in_scope),
            "operations_attempted": len(self.attempted),
            "operations_succeeded": len(self.succeeded),
            "operation_attempt_coverage": self.attempt_ratio,
            "operation_success_coverage": self.success_ratio,
            "requests": self.requests,
            "matched_requests": self.matched_requests,
            "unmatched_requests": self.unmatched_requests,
            "unanswered_requests": self.unanswered_requests,
            "never_attempted": sorted(self.in_scope - self.attempted),
            "attempted_never_succeeded": sorted(self.attempted - self.succeeded),
            "status_classes": {k: dict(v) for k, v in sorted(self.status_classes.items())},
        }


def status_class(status: int | None) -> str:
    return "none" if status is None else f"{status // 100}xx"


def operation_coverage(
    spec: OpenApiSpec,
    interactions: Iterable[HttpInteraction],
    success: SuccessCriterion,
    excluded: Iterable[str] = (),
) -> OperationCoverage:
    """``excluded`` operation keys are removed from the scope (e.g. a logout endpoint that
    the protocol rules out); the exclusion must be reported with the results."""
    in_scope = frozenset(op.key for op in spec.operations) - frozenset(excluded)
    attempted: set[str] = set()
    succeeded: set[str] = set()
    classes: dict[str, Counter[str]] = defaultdict(Counter)
    requests = matched = unanswered = 0
    for interaction in interactions:
        requests += 1
        if not interaction.answered:
            unanswered += 1
        operation = spec.match(interaction.method, interaction.target).operation
        if operation is None or operation.key not in in_scope:
            continue
        matched += 1
        attempted.add(operation.key)
        classes[operation.key][status_class(interaction.status)] += 1
        if success(interaction.status):
            succeeded.add(operation.key)
    return OperationCoverage(
        in_scope=in_scope,
        attempted=frozenset(attempted),
        succeeded=frozenset(succeeded),
        status_classes={key: dict(counter) for key, counter in classes.items()},
        requests=requests,
        matched_requests=matched,
        unanswered_requests=unanswered,
    )
