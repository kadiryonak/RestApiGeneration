import json
from pathlib import Path

import pytest

from restgen.errors import RestgenError
from restgen.evaluation.report import build_report, collect


def _metrics(service: str, category: str, seed: int, success: float, line: float) -> dict:  # type: ignore[type-arg]
    return {
        "service": service,
        "category": category,
        "seed": seed,
        "operations": {"operation_success_coverage": success, "operation_attempt_coverage": 1.0},
        "exploration_coverage": {"line_coverage": line, "branch_coverage": None},
        "faults": {"unique_failures": 1, "unique_crash_locations": 1},
        "suite": None,
        "output_coverage": None,
        "retention": None,
        "cost": {"http_calls": 100, "wall_seconds": 20.0},
    }


def _write(
    root: Path, tool: str, service: str, category: str, values: list[tuple[float, float]]
) -> None:
    for seed, (success, line) in enumerate(values, start=42):
        directory = root / "runs" / "exp" / service / tool / f"s{seed}"
        directory.mkdir(parents=True)
        (directory / "metrics.json").write_text(
            json.dumps(_metrics(service, category, seed, success, line))
        )


def test_report_compares_groups_and_separates_categories(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "a",
        "real1",
        "real",
        [(0.2, 0.5), (0.25, 0.5), (0.2, 0.55), (0.3, 0.5), (0.2, 0.52)],
    )
    _write(
        tmp_path,
        "b",
        "real1",
        "real",
        [(0.8, 0.9), (0.85, 0.9), (0.9, 0.95), (0.8, 0.9), (0.9, 0.91)],
    )
    _write(tmp_path, "a", "toy", "artificial", [(1.0, 1.0), (1.0, 1.0)])
    _write(tmp_path, "b", "toy", "artificial", [(1.0, 1.0), (1.0, 1.0)])
    data, categories = collect(tmp_path, {"a": ["exp/*/a/*"], "b": ["exp/*/b/*"]})
    assert categories == {"real1": "real", "toy": "artificial"}
    assert data["b"]["real1"]["operation_success_coverage"] == [0.8, 0.85, 0.9, 0.8, 0.9]
    assert "branch_coverage" not in data["a"]["real1"]  # undefined values are not invented

    markdown, payload = build_report("demo", data, categories)
    comparison = payload["comparisons"]["operation_success_coverage"]["b|real1"]
    assert comparison["a12"] == 1.0
    assert comparison["p_holm"] < 0.05
    assert payload["comparisons"]["line_coverage"]["b|toy"]["p_value"] == 1.0
    assert payload["aggregates"]["real"]["operation_success_coverage"]["b"] == 0.85
    assert "artificial" in payload["aggregates"]
    assert "## real1 (real)" in markdown
    assert "A12=1.00 (large)" in markdown


def test_empty_group_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(RestgenError, match=r"no metrics\.json"):
        collect(tmp_path, {"x": ["nothing/*"]})
