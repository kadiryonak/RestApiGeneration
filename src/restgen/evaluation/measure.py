"""Compute ``metrics.json`` for one run directory from its recorded artefacts only.

Re-runnable at any time (e.g. after editing ``triage.toml``); nothing here talks to a
service or a tool.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from restgen.coverage.models import CodeCoverage
from restgen.evaluation.cost import Cost
from restgen.evaluation.faults import TRIAGE_FILE, fault_funnel, write_triage_template
from restgen.evaluation.operations import SuccessCriterion, operation_coverage
from restgen.evaluation.retention import CoverageRetention
from restgen.evaluation.suite import TestResult, read_junit, suite_quality
from restgen.jsonio import read_json, write_json
from restgen.openapi import OpenApiSpec
from restgen.runner import load_run
from restgen.traffic.models import TRAFFIC_FILE, read_traffic

METRICS_FILE = "metrics.json"


def measure(directory: Path, source_root: Path | None = None) -> dict[str, Any]:
    run = load_run(directory)
    settings = run["settings"]["evaluation"]
    spec = OpenApiSpec(read_json(directory / "openapi.json"))
    exploration = directory / "exploration"
    traffic = list(read_traffic(exploration / TRAFFIC_FILE))

    operations = operation_coverage(
        spec,
        traffic,
        SuccessCriterion(settings["success_status_min"], settings["success_status_max"]),
    )
    write_triage_template(
        directory / TRIAGE_FILE,
        fault_funnel(
            spec, traffic, settings["server_error_min"], directory / TRIAGE_FILE
        ).unique_failures,
    )
    log = exploration / "service.log"
    faults = fault_funnel(
        spec,
        traffic,
        settings["server_error_min"],
        directory / TRIAGE_FILE,
        server_log=log.read_text(encoding="utf-8", errors="replace") if log.is_file() else "",
        source_root=source_root,
    )

    exploration_coverage = _coverage(exploration)
    metrics: dict[str, Any] = {
        "run_id": run["run_id"],
        "service": run["service"],
        "tool": run["tool"]["tool"],
        "tool_version": run["tool"]["version"],
        "seed": run["seed"],
        "category": run["category"],
        "operations": operations.summary(),
        "exploration_coverage": exploration_coverage.summary() if exploration_coverage else None,
        "faults": faults.summary(),
        "suite": None,
        "output_coverage": None,
        "retention": None,
    }

    tests = [Path(p) for p in run["tool"]["tests"]]
    reruns = sorted((directory / "output").glob("rerun-*"), key=lambda p: int(p.name[6:]))
    tests_in_output: int | None = None
    if tests:
        # Reference run: the tool's own execution of its suite when it has one (Hypothesis),
        # otherwise the first clean re-execution (EvoMaster).
        runs: list[list[TestResult]] = []
        if "junit" in run["tool"]["reports"]:
            runs.append(read_junit(Path(run["tool"]["reports"]["junit"])))
        runs += [read_junit(r / "junit.xml") for r in reruns if (r / "junit.xml").is_file()]
        quality = suite_quality(tests, {Path(k): v for k, v in run["collectable"].items()}, runs)
        metrics["suite"] = quality.summary()
        tests_in_output = quality.tests
        output_coverage = _coverage(reruns[0]) if reruns else None
        if output_coverage is not None:
            metrics["output_coverage"] = output_coverage.summary()
            if exploration_coverage is not None:
                metrics["retention"] = CoverageRetention(
                    exploration_coverage, output_coverage
                ).summary()

    metrics["cost"] = Cost(
        wall_seconds=run["tool"]["wall_seconds"],
        http_calls=len(traffic),
        tests_in_output=tests_in_output,
    ).summary()
    write_json(directory / METRICS_FILE, metrics)
    return metrics


def _coverage(directory: Path) -> CodeCoverage | None:
    path = directory / "coverage.normalized.json"
    if not path.is_file():
        return None
    return CodeCoverage.from_record(json.loads(path.read_text(encoding="utf-8")))
