"""Mutation score (analysis §5.6).

    MS = killed valid, non-equivalent mutants / evaluated valid, non-equivalent mutants

Two families are never mixed in one score:

* RESPONSE mutants alter the *response data* (AGORA+): does the oracle notice a corrupted
  output?
* IMPLEMENTATION mutants alter the *service's behaviour* (RESTestBench): does the test
  tell a faulty implementation from the reference one?

A mutant counts as killed only if the test passed on the reference service and failed on
the mutant *on an assertion*. Syntax/import errors, an unreachable server or a timeout are
not kills. Mutants of unknown equivalence are excluded and reported.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from restgen.coverage.models import ratio
from restgen.errors import MeasurementError


class MutantFamily(StrEnum):
    RESPONSE = "response"
    IMPLEMENTATION = "implementation"


class MutantRun(StrEnum):
    ASSERTION_FAILED = "assertion_failed"
    PASSED = "passed"
    OTHER_FAILURE = "other_failure"  # exception before/outside the oracle
    ERROR = "error"  # syntax/import/collection error
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"  # the mutated service did not answer


@dataclass(frozen=True)
class MutantResult:
    mutant_id: str
    family: MutantFamily
    valid: bool  # the mutant builds and the service starts
    equivalent: bool | None  # None: not established
    reference_passed: bool  # the killing test(s) passed on the unmutated service
    run: MutantRun

    @property
    def evaluated(self) -> bool:
        return self.valid and self.equivalent is False

    @property
    def killed(self) -> bool:
        return self.evaluated and self.reference_passed and self.run is MutantRun.ASSERTION_FAILED


@dataclass(frozen=True)
class MutationScore:
    family: MutantFamily
    evaluated: int
    killed: int
    invalid: int
    equivalent: int
    unknown_equivalence: int
    not_counted_failures: int  # evaluated mutants that "failed" for a non-assertion reason

    @property
    def score(self) -> float | None:
        return ratio(self.killed, self.evaluated)

    def summary(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "mutation_score": self.score,
            "killed": self.killed,
            "evaluated": self.evaluated,
            "invalid": self.invalid,
            "equivalent": self.equivalent,
            "unknown_equivalence": self.unknown_equivalence,
            "not_counted_failures": self.not_counted_failures,
        }


def mutation_score(results: Iterable[MutantResult]) -> MutationScore:
    results = list(results)
    families = {r.family for r in results}
    if len(families) != 1:
        raise MeasurementError("a mutation score needs results of exactly one mutant family")
    evaluated = [r for r in results if r.evaluated]
    return MutationScore(
        family=families.pop(),
        evaluated=len(evaluated),
        killed=sum(r.killed for r in evaluated),
        invalid=sum(not r.valid for r in results),
        equivalent=sum(r.valid and r.equivalent is True for r in results),
        unknown_equivalence=sum(r.valid and r.equivalent is None for r in results),
        not_counted_failures=sum(
            r.run
            in (MutantRun.OTHER_FAILURE, MutantRun.ERROR, MutantRun.TIMEOUT, MutantRun.UNREACHABLE)
            for r in evaluated
        ),
    )
