"""Both comparison tools against the real booking service, measured end to end.

Needs `make tools` and `restgen benchmark setup -s booking`; skipped otherwise.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from restgen.benchmark.fetcher import SuiteFetcher
from restgen.benchmark.registry import BenchmarkRegistry
from restgen.benchmark.service import ServiceEnvironment
from restgen.config import load_settings
from restgen.evaluation.measure import measure
from restgen.runner import Runner, RunRequest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def runner(tmp_path_factory: pytest.TempPathFactory) -> Runner:
    settings = load_settings(
        ROOT,
        overrides=[
            "budget.max_time_seconds=5",
            "budget.max_examples=10",
            "evaluation.rerun_count=2",
        ],
    )
    settings = replace(
        settings,
        paths=replace(settings.paths, results_dir=tmp_path_factory.mktemp("results")),
    )
    registry = BenchmarkRegistry.load(settings.paths.benchmark_manifest)
    service = registry.service("booking")
    suite_ok = SuiteFetcher(settings.paths.benchmark_dir).verify(registry.suite(service.suite)).ok
    if not (suite_ok and ServiceEnvironment(service, settings.paths.benchmark_dir).ready):
        pytest.skip("booking not set up (restgen benchmark setup -s booking)")
    tools_ready = (
        settings.schemathesis.executable.is_file()
        and settings.hypothesis.python.is_file()
        and settings.evomaster.jar.is_file()
        and settings.evomaster.python.is_file()
    )
    if not tools_ready:
        pytest.skip("comparison tools not installed (make tools)")
    return Runner(settings, registry)


def _source_root(runner: Runner) -> Path:
    service = runner.registry.service("booking")
    suite = runner.fetcher.path(runner.registry.suite(service.suite))
    return suite / service.launch.workdir


def test_schemathesis_run_is_measured(runner: Runner) -> None:
    directory = runner.run(RunRequest("it", "booking", "schemathesis", 42))
    metrics = measure(directory, _source_root(runner))
    assert metrics["operations"]["operations_in_scope"] == 3
    assert metrics["operations"]["requests"] > 0
    assert metrics["exploration_coverage"]["line_coverage"] > 0
    # the example's deliberate KeyError on an unknown room type
    assert metrics["faults"]["unique_failures"] >= 1
    assert any("KeyError @ app.py" in loc for loc in _crashes(directory, runner))
    assert metrics["suite"] is None  # no persistent suite
    assert (directory / "triage.toml").is_file()
    assert (directory / "tool" / ".schemathesis").is_dir()  # crash cache stays per run
    assert not (ROOT / ".schemathesis").exists()
    # a complete run is never redone silently
    assert runner.run(RunRequest("it", "booking", "schemathesis", 42)) == directory


def test_hypothesis_suite_is_rerun_on_clean_services(runner: Runner) -> None:
    directory = runner.run(RunRequest("it", "booking", "hypothesis", 42))
    metrics = measure(directory, _source_root(runner))
    suite = metrics["suite"]
    assert suite["tests"] == 3
    assert suite["collectable_rate"] == 1.0
    assert suite["reruns"] == 3  # the exploration run + 2 clean re-executions
    assert metrics["output_coverage"]["line_coverage"] > 0
    assert metrics["retention"]["line_retention"] is not None
    assert len(list((directory / "output").glob("rerun-*/traffic.jsonl"))) == 2


def test_evomaster_suite_hard_codes_the_proxy_and_still_reruns(runner: Runner) -> None:
    directory = runner.run(RunRequest("it", "booking", "evomaster", 42))
    metrics = measure(directory, _source_root(runner))
    assert metrics["faults"]["unique_failures"] >= 1
    suite = metrics["suite"]
    assert suite["tests"] >= 1
    assert suite["reruns"] == 2  # no own reference run: both clean re-executions
    # every rerun reached the clean service through the reused proxy port
    for traffic in (directory / "output").glob("rerun-*/traffic.jsonl"):
        assert traffic.stat().st_size > 0
    # EvoMaster's working files stay inside the run directory
    assert (directory / "tool" / "em.yaml").is_file()


def _crashes(directory: Path, runner: Runner) -> list[str]:
    from restgen.evaluation.faults import crash_locations

    log = (directory / "exploration" / "service.log").read_text()
    return list(crash_locations(log, _source_root(runner)))
