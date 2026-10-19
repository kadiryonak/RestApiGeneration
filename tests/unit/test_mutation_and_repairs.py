import pytest

from restgen.errors import MeasurementError
from restgen.evaluation.cost import Cost
from restgen.evaluation.mutation import MutantFamily, MutantResult, MutantRun, mutation_score
from restgen.evaluation.repairs import (
    ExpectationSource,
    RepairKind,
    RepairRecord,
    repair_summary,
)

IMPL = MutantFamily.IMPLEMENTATION


def _m(
    i: str, run: MutantRun, valid: bool = True, eq: bool | None = False, ref: bool = True
) -> MutantResult:
    return MutantResult(i, IMPL, valid, eq, ref, run)


def test_only_assertion_failures_on_passing_reference_kill() -> None:
    score = mutation_score(
        [
            _m("1", MutantRun.ASSERTION_FAILED),  # killed
            _m("2", MutantRun.PASSED),  # survived
            _m("3", MutantRun.TIMEOUT),  # not a kill
            _m("4", MutantRun.ASSERTION_FAILED, ref=False),  # test broken on reference
            _m("5", MutantRun.ASSERTION_FAILED, valid=False),  # excluded
            _m("6", MutantRun.PASSED, eq=True),  # equivalent: excluded
            _m("7", MutantRun.PASSED, eq=None),  # unknown: excluded and reported
        ]
    )
    assert score.evaluated == 4
    assert score.killed == 1
    assert score.score == 0.25
    assert score.invalid == 1
    assert score.equivalent == 1
    assert score.unknown_equivalence == 1
    assert score.not_counted_failures == 1


def test_families_are_never_mixed() -> None:
    response = MutantResult("r", MutantFamily.RESPONSE, True, False, True, MutantRun.PASSED)
    with pytest.raises(MeasurementError):
        mutation_score([_m("1", MutantRun.PASSED), response])
    with pytest.raises(MeasurementError):
        mutation_score([])


def test_repair_drift_and_cost() -> None:
    records = [
        RepairRecord("t1", 1, RepairKind.REQUEST_PREPARATION, None),
        RepairRecord("t1", 2, RepairKind.ASSERTION_SEMANTICS, ExpectationSource.OBSERVED_RESPONSE),
        RepairRecord("t2", 1, RepairKind.ASSERTION_SEMANTICS, ExpectationSource.REQUIREMENT),
    ]
    summary = repair_summary(records)
    assert summary["repairs"] == 3
    assert summary["assertion_changes_from_observed_responses"] == 1
    assert Cost(1.5, 10).summary()["tests_in_output"] is None
