"""The interface every compared tool implements."""

from __future__ import annotations

import json
import os
import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from restgen.config import BudgetSettings
from restgen.errors import ToolError


@dataclass(frozen=True)
class ToolRunContext:
    base_url: str  # the recording proxy, never the service directly
    openapi_url: str  # where the tool reads the schema (through the proxy, or a file)
    headers: Mapping[str, str]  # fixed request headers (e.g. auth), same for every tool
    seed: int
    budget: BudgetSettings
    output_dir: Path  # the tool's own artefacts (reports, generated tests)
    # Path prefix of the API from the OpenAPI document ("/api/v1"); tools whose base-URL
    # option replaces the document's servers (Schemathesis --url) must append it.
    api_base_path: str = ""


@dataclass(frozen=True)
class ToolRunResult:
    tool: str
    version: str
    command: tuple[str, ...]
    exit_code: int
    wall_seconds: float
    tests: tuple[Path, ...] = ()  # persistent test files; empty for tools without a suite
    reports: Mapping[str, Path] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "version": self.version,
            "command": list(self.command),
            "exit_code": self.exit_code,
            "wall_seconds": self.wall_seconds,
            "tests": [str(p) for p in self.tests],
            "reports": {k: str(v) for k, v in self.reports.items()},
        }


class ComparisonTool(ABC):
    name: str

    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def run(self, context: ToolRunContext) -> ToolRunResult:
        """Explore the API through ``context.base_url`` within the budget."""

    @property
    def produces_suite(self) -> bool:
        return False

    def collect(self, tests: Sequence[Path]) -> dict[Path, bool]:
        """Whether pytest collects each test file (only for suite-producing tools)."""
        raise ToolError(f"{self.name} does not produce a test suite")

    def execute_suite(
        self, tests: Sequence[Path], base_url: str, headers: Mapping[str, str], junit: Path
    ) -> int:
        """Re-run the saved suite alone against ``base_url``; returns pytest's exit code."""
        raise ToolError(f"{self.name} does not produce a test suite")


def run_command(
    argv: Sequence[str],
    log: Path,
    timeout: float,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> tuple[int, float]:
    """Run a tool process, stdout+stderr to ``log``; returns (exit code, wall seconds)."""
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        with log.open("wb") as handle:
            result = subprocess.run(
                list(argv),
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                env=dict(env) if env is not None else None,
                cwd=cwd,
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"{argv[0]} exceeded its hard timeout of {timeout:.0f}s") from exc
    except OSError as exc:
        raise ToolError(f"cannot start {argv[0]}: {exc}") from exc
    return result.returncode, time.perf_counter() - started


def capture(argv: Sequence[str]) -> str:
    try:
        result = subprocess.run(list(argv), capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolError(f"cannot run {argv[0]}: {exc}") from exc
    if result.returncode != 0:
        raise ToolError(f"{' '.join(argv)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


class PytestSuiteTool(ComparisonTool):
    """A tool whose output is a persistent suite that pytest can run (pytest also runs
    unittest classes). The suite gets its target through RESTGEN_* environment variables;
    suites that hard-code the URL instead rely on the runner reusing the proxy port."""

    @property
    @abstractmethod
    def python(self) -> Path:
        """Interpreter of the environment the suite runs in."""

    @property
    def produces_suite(self) -> bool:
        return True

    def _python(self) -> str:
        if not self.python.is_file():
            raise ToolError(
                f"{self.name}: test environment missing at {self.python}; run `make tools`"
            )
        return str(self.python)

    def collect(self, tests: Sequence[Path]) -> dict[Path, bool]:
        result = {}
        for test in tests:
            code, _ = run_command(
                [
                    self._python(),
                    "-m",
                    "pytest",
                    "--collect-only",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    str(test),
                ],
                test.parent / f".{test.stem}.collect.log",
                timeout=120,
                env=suite_env("http://127.0.0.1:9", {}, 1.0),
                cwd=test.parent,
            )
            result[test] = code == 0
        return result

    def execute_suite(
        self, tests: Sequence[Path], base_url: str, headers: Mapping[str, str], junit: Path
    ) -> int:
        code, _ = run_command(
            self.pytest_argv(tests, junit),
            junit.with_suffix(".log"),
            timeout=3600,
            env=suite_env(base_url, headers, 10.0),
            cwd=tests[0].parent,
        )
        check_pytest_exit(code, junit.parent)
        return code

    def pytest_argv(self, tests: Sequence[Path], junit: Path) -> list[str]:
        return [
            self._python(),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
            *(str(t) for t in tests),
        ]


def suite_env(base_url: str, headers: Mapping[str, str], timeout: float) -> dict[str, str]:
    return {
        **os.environ,
        "RESTGEN_BASE_URL": base_url,
        "RESTGEN_HEADERS": json.dumps(dict(headers)),
        "RESTGEN_REQUEST_TIMEOUT": str(timeout),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def check_pytest_exit(code: int, where: Path) -> None:
    # 0 all passed, 1 some tests failed (= findings); anything else is a harness problem.
    if code not in (0, 1):
        raise ToolError(f"pytest exited with {code}; see {where}")
