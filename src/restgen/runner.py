"""One measured run: (service, tool, seed) → a self-describing run directory.

    results/runs/<run_id>/<service>/<tool>/s<seed>/
      run.json                 what ran: commits, versions, command, seed, config
      openapi.json             the exact schema the run used
      exploration/             the tool's run: traffic.jsonl, coverage.json, service.log
      tool/                    the tool's own artefacts (reports, generated suite, logs)
      output/rerun-<i>/        the saved suite re-run alone on a clean service
      triage.toml, metrics.json  written by `restgen measure`

Every service start is fresh (new process, new coverage data), and every tool talks to
the service through the recording proxy, so all tools are measured the same way.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from restgen.baselines.base import ComparisonTool, ToolRunContext
from restgen.baselines.hypothesis_pytest import HypothesisPytest
from restgen.baselines.schemathesis_cli import SchemathesisCli
from restgen.benchmark.fetcher import SuiteFetcher
from restgen.benchmark.models import CoverageKind, Service
from restgen.benchmark.registry import BenchmarkRegistry
from restgen.benchmark.service import ServiceEnvironment, ServiceProcess
from restgen.config import Settings
from restgen.errors import BenchmarkError, RestgenError, ToolError
from restgen.jsonio import append_jsonl, write_json
from restgen.openapi import OpenApiSpec
from restgen.traffic.models import TRAFFIC_FILE
from restgen.traffic.proxy import RecordingProxy

TOOLS = ("schemathesis", "hypothesis")
RUN_RECORD = "run.json"


@dataclass(frozen=True)
class RunRequest:
    run_id: str
    service: str
    tool: str
    seed: int


def run_directory(settings: Settings, request: RunRequest) -> Path:
    return (
        settings.paths.results_dir
        / "runs"
        / request.run_id
        / request.service
        / request.tool
        / f"s{request.seed}"
    )


def make_tool(name: str, settings: Settings, spec: OpenApiSpec) -> ComparisonTool:
    if name == "schemathesis":
        return SchemathesisCli(settings.schemathesis)
    if name == "hypothesis":
        return HypothesisPytest(settings.hypothesis, spec)
    raise ToolError(f"unknown tool {name!r}; known: {', '.join(TOOLS)}")


class Runner:
    def __init__(self, settings: Settings, registry: BenchmarkRegistry) -> None:
        self.settings = settings
        self.registry = registry
        self.fetcher = SuiteFetcher(settings.paths.benchmark_dir)

    def run(self, request: RunRequest, force: bool = False) -> Path:
        directory = run_directory(self.settings, request)
        if (directory / RUN_RECORD).is_file() and not force:
            return directory  # complete runs are never silently overwritten
        if directory.exists() and any(directory.iterdir()) and not force:
            raise RestgenError(f"incomplete run directory {directory}; rerun with --force")
        directory.mkdir(parents=True, exist_ok=True)
        service = self.registry.service(request.service)
        suite = self.registry.suite(service.suite)
        status = self.fetcher.verify(suite)
        if not status.ok:
            raise BenchmarkError(f"suite {suite.name} is not fetched at its pinned commit")
        environment = ServiceEnvironment(service, self.settings.paths.benchmark_dir)
        started = time.time()
        append_jsonl(
            directory.parent / "invocations.jsonl",
            {"seed": request.seed, "started_at": started, "force": force},
        )

        exploration = directory / "exploration"
        with self._service(service, environment, status.path, exploration) as process:
            spec, openapi_source = self._load_spec(service, status.path, process.base_url)
            write_json(directory / "openapi.json", dict(spec.document))
            tool = make_tool(request.tool, self.settings, spec)
            with RecordingProxy(
                process.base_url,
                exploration / TRAFFIC_FILE,
                self.settings.proxy,
                self.settings.budget.request_timeout_seconds,
            ) as proxy:
                openapi_url = (
                    openapi_source if service.openapi_is_file else proxy.url + service.openapi
                )
                result = tool.run(
                    ToolRunContext(
                        base_url=proxy.url,
                        openapi_url=openapi_url,
                        headers=service.headers,
                        seed=request.seed,
                        budget=self.settings.budget,
                        output_dir=directory / "tool",
                    )
                )
        self._export(process, exploration)

        reruns: list[dict[str, Any]] = []
        collectable: dict[str, bool] = {}
        if tool.produces_suite and result.tests:
            collectable = {str(k): v for k, v in tool.collect(result.tests).items()}
            for index in range(1, self.settings.evaluation.rerun_count + 1):
                rerun = directory / "output" / f"rerun-{index}"
                with (
                    self._service(service, environment, status.path, rerun) as clean,
                    RecordingProxy(
                        clean.base_url,
                        rerun / TRAFFIC_FILE,
                        self.settings.proxy,
                        self.settings.budget.request_timeout_seconds,
                    ) as proxy,
                ):
                    code = tool.execute_suite(
                        result.tests, proxy.url, service.headers, rerun / "junit.xml"
                    )
                self._export(clean, rerun)
                reruns.append({"index": index, "exit_code": code})

        write_json(
            directory / RUN_RECORD,
            {
                "run_id": request.run_id,
                "service": service.name,
                "suite": {"name": suite.name, "commit": suite.commit},
                "category": service.category.value,
                "role": service.role.value,
                "seed": request.seed,
                "tool": result.to_record(),
                "collectable": collectable,
                "reruns": reruns,
                "openapi_version": spec.version,
                "settings": self.settings.to_dict(),
                "restgen_commit": _git_state(self.settings.root),
                "started_at": started,
                "finished_at": time.time(),
            },
        )
        return directory

    def _service(
        self, service: Service, environment: ServiceEnvironment, suite_path: Path, where: Path
    ) -> ServiceProcess:
        coverage = where / ".coverage" if service.coverage.kind is CoverageKind.COVERAGEPY else None
        return ServiceProcess(service, environment, suite_path, where / "service.log", coverage)

    @staticmethod
    def _export(process: ServiceProcess, where: Path) -> None:
        if process.coverage_data is not None:
            coverage = process.export_coverage(where / "coverage.json")
            write_json(where / "coverage.normalized.json", coverage.to_record())

    @staticmethod
    def _load_spec(service: Service, suite_path: Path, base_url: str) -> tuple[OpenApiSpec, str]:
        if service.openapi_is_file:
            path = suite_path / service.openapi.removeprefix("file:")
            return OpenApiSpec.load(path), str(path)
        # Loaded directly (not through the proxy) so it is not part of the tool's traffic.
        url = base_url + service.openapi
        return OpenApiSpec.load(url), url


def _git_state(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        )
        return result.stdout.strip()

    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def load_run(directory: Path) -> dict[str, Any]:
    path = directory / RUN_RECORD
    if not path.is_file():
        raise RestgenError(f"not a complete run directory: {directory}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
