"""The interface every compared tool implements."""

from __future__ import annotations

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
