"""Oracle drift during self-repair (analysis §5.7).

When a generator repairs a failing test it may "fix" the expectation so that it matches
wrong behaviour. Every repair records what it changed and where the new expectation came
from, so drift can be measured instead of assumed away.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RepairKind(StrEnum):
    REQUEST_PREPARATION = "request_preparation"  # URL, headers, body shape, auth
    DATA_DEPENDENCY = "data_dependency"  # ids / resources created by earlier calls
    ASSERTION_SEMANTICS = "assertion_semantics"  # what the test expects
    OTHER = "other"


class ExpectationSource(StrEnum):
    REQUIREMENT = "requirement"  # spec / NL requirement (independent of the implementation)
    OBSERVED_RESPONSE = "observed_response"  # copied from what the service returned


@dataclass(frozen=True)
class RepairRecord:
    test_id: str
    round: int
    kind: RepairKind
    expectation_source: ExpectationSource | None  # only for ASSERTION_SEMANTICS

    @property
    def drift_risk(self) -> bool:
        return (
            self.kind is RepairKind.ASSERTION_SEMANTICS
            and self.expectation_source is ExpectationSource.OBSERVED_RESPONSE
        )


def repair_summary(records: Iterable[RepairRecord]) -> dict[str, Any]:
    records = list(records)
    return {
        "repairs": len(records),
        "by_kind": dict(Counter(r.kind.value for r in records)),
        "assertion_changes_from_observed_responses": sum(r.drift_risk for r in records),
    }
