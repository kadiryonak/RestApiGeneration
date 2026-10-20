from pathlib import Path

import pytest

from restgen.errors import MeasurementError
from restgen.telemetry.trace import SearchTrace, read_trace, trace_summary


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_trace_records_phases_operators_and_discoveries(tmp_path: Path) -> None:
    clock = FakeClock()
    trace = SearchTrace(tmp_path / "search_trace.jsonl", clock=clock, wall_clock=lambda: 0.0)
    with trace.phase("init"):
        clock.now += 2.0
        trace.evaluation(
            "c1", "random", ["POST /a"], http_calls=1, new_targets=["op:POST /a"], fitness=1.0
        )
    with trace.phase("employed", cycle=1):
        clock.now += 3.0
        trace.evaluation(
            "c2", "phi", ["POST /a", "GET /a/{id}"], http_calls=2, new_targets=[], fitness=1.0
        )
        trace.evaluation(
            "c3",
            "llm",
            ["POST /a"],
            http_calls=1,
            new_targets=["op:GET /a/{id}", "status:GET /a/{id}:200"],
            fitness=3.0,
        )
        trace.improvement("c3", "llm", before=1.0, after=3.0)
    with trace.phase("scout"):
        clock.now += 1.0
        trace.abandon("c2", trials=5)
    trace.checkpoint(evaluations=3, http_calls=4)
    trace.finish()

    summary = trace_summary(read_trace(tmp_path / "search_trace.jsonl"))
    assert summary["finished"]
    assert summary["search_seconds"] == 6.0
    assert summary["evaluations"] == 3
    assert summary["http_calls"] == 4
    assert summary["abandoned"] == 1
    assert summary["phases"]["employed"] == {"count": 1, "seconds": 3.0, "evaluations": 2}
    assert summary["phases"]["init"]["seconds"] == 2.0
    assert summary["origins"]["llm"]["improvements"] == 1
    assert summary["origins"]["llm"]["improvement_rate"] == 1.0
    assert summary["origins"]["phi"]["improvement_rate"] == 0.0
    assert summary["targets_reached"] == 3
    assert summary["target_discovery_curve"] == [[2.0, 1], [5.0, 2], [5.0, 3]]


def test_phases_do_not_nest_and_trace_needs_start(tmp_path: Path) -> None:
    trace = SearchTrace(tmp_path / "t.jsonl")
    with pytest.raises(MeasurementError), trace.phase("employed"), trace.phase("onlooker"):
        pass
    with pytest.raises(MeasurementError):
        trace_summary([{"kind": "evaluation"}])
    with pytest.raises(MeasurementError):
        read_trace(tmp_path / "missing.jsonl")
