from pathlib import Path

import pytest

from restgen.instrumentation.python import (
    PythonInstrumentation,
    branch_distances,
    instrument_source,
    instrumentation_globals,
    state_access,
)


def test_numeric_branch_distance_gives_gradient_for_uncovered_outcome() -> None:
    result, true_distance, false_distance = branch_distances(8, "Gt", 10)
    assert not result
    assert true_distance == 3.0
    assert false_distance == 0.0


def test_string_equality_uses_edit_distance() -> None:
    result, true_distance, false_distance = branch_distances("ADMIN", "Eq", "ADMIT")
    assert not result
    assert true_distance == 1.0
    assert false_distance == 0.0


def test_ast_probes_and_line_tracing_produce_live_scores(tmp_path: Path) -> None:
    source = """\
def classify(value):
    if value > 10:
        return 'large'
    return 'small'
"""
    filename = str(tmp_path / "target.py")
    namespace = instrumentation_globals()
    with PythonInstrumentation([tmp_path]) as recorder:
        exec(instrument_source(source, filename), namespace)
        assert namespace["classify"](8) == "small"

    true_targets = [key for key in recorder.scores if key.endswith(":true")]
    false_targets = [key for key in recorder.scores if key.endswith(":false")]
    assert len(true_targets) == len(false_targets) == 1
    assert recorder.scores[true_targets[0]] == pytest.approx(0.25)
    assert recorder.scores[false_targets[0]] == 1.0
    assert any(key.startswith("line:target.py:") for key in recorder.scores)


def test_python_state_access_is_tied_to_current_candidate() -> None:
    with PythonInstrumentation([]) as recorder:
        state_access("POST /orders", "users")
    assert recorder.state_accesses == {"POST /orders": {"users"}}
