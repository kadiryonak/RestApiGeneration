"""Time-based metrics from the proxy recording; they apply to every tool alike.

All times are seconds since the tool was started (``origin``):

* per operation: first attempt and first success;
* time to first failure (TTFF) and first occurrence of every unique failure;
* step curves of operations attempted / succeeded and unique failures over time;
* the normalised area under the success-coverage curve over the time budget: 1.0 means
  every in-scope operation succeeded at t = 0, so two tools that end at the same coverage
  are told apart by how fast they got there.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from restgen.evaluation.faults import failure_signature
from restgen.evaluation.operations import SuccessCriterion
from restgen.openapi import OpenApiSpec
from restgen.traffic.models import HttpInteraction


@dataclass(frozen=True)
class Timeline:
    first_attempt: dict[str, float]
    first_success: dict[str, float]
    first_failure: dict[str, float]  # failure signature -> first time
    in_scope: int
    budget_seconds: float

    def curve(self, firsts: dict[str, float]) -> list[list[float]]:
        """Step curve [[t, cumulative count], ...]."""
        return [[t, i + 1] for i, t in enumerate(sorted(firsts.values()))]

    def area_under_success(self) -> float | None:
        """Normalised AUC of operation success coverage over [0, budget]."""
        if self.in_scope == 0 or self.budget_seconds <= 0:
            return None
        area = sum(
            max(0.0, self.budget_seconds - min(t, self.budget_seconds))
            for t in self.first_success.values()
        )
        return area / (self.in_scope * self.budget_seconds)

    def summary(self) -> dict[str, Any]:
        failures = sorted(self.first_failure.values())
        return {
            "budget_seconds": self.budget_seconds,
            "time_to_first_failure": failures[0] if failures else None,
            "time_to_last_new_success": max(self.first_success.values(), default=None),
            "success_coverage_auc": self.area_under_success(),
            "first_success": dict(sorted(self.first_success.items(), key=lambda kv: kv[1])),
            "attempted_curve": self.curve(self.first_attempt),
            "success_curve": self.curve(self.first_success),
            "failure_curve": self.curve(self.first_failure),
        }


def timeline(
    spec: OpenApiSpec,
    interactions: Sequence[HttpInteraction],
    success: SuccessCriterion,
    server_error_min: int,
    origin: float | None,
    budget_seconds: float,
) -> Timeline:
    """``origin``: unix time the tool was started; defaults to the first request."""
    start = origin if origin is not None else min((i.started_at for i in interactions), default=0.0)
    in_scope = {op.key for op in spec.operations}
    attempt: dict[str, float] = {}
    succeeded: dict[str, float] = {}
    failed: dict[str, float] = {}
    for interaction in sorted(interactions, key=lambda i: i.started_at):
        t = round(max(0.0, interaction.started_at - start), 3)
        matched = spec.match(interaction.method, interaction.target)
        if matched.operation is not None and matched.operation.key in in_scope:
            key = matched.operation.key
            attempt.setdefault(key, t)
            if success(interaction.status):
                succeeded.setdefault(key, t)
        if interaction.status is not None and interaction.status >= server_error_min:
            name = (
                matched.operation.key
                if matched.operation
                else f"UNMATCHED {interaction.method} {matched.path}"
            )
            failed.setdefault(
                failure_signature(name, interaction.status, interaction.response_body), t
            )
    return Timeline(attempt, succeeded, failed, len(in_scope), budget_seconds)
