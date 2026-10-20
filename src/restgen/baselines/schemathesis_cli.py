"""Schemathesis as an *application*: ``schemathesis run`` against the live API.

Flags follow Schemathesis' own benchmarking guide (docs/guides/benchmarking.md): the run
is bounded by the clock (``--max-time``), keeps going after failures, skips shrinking and
suppresses health checks (configured in ``tools.schemathesis.extra_args``). The tool
produces reports, not a persistent pytest suite, so suite metrics do not apply to it.
"""

from __future__ import annotations

from pathlib import Path

from restgen.baselines.base import (
    ComparisonTool,
    ToolRunContext,
    ToolRunResult,
    capture,
    run_command,
)
from restgen.config import SchemathesisSettings
from restgen.errors import ToolError

REPORT_FORMATS = ("junit", "har", "ndjson", "json")
# Grace period on top of --max-time for loading the schema and writing reports.
HARD_TIMEOUT_MARGIN_SECONDS = 300


class SchemathesisCli(ComparisonTool):
    name = "schemathesis"

    def __init__(self, settings: SchemathesisSettings) -> None:
        self._settings = settings

    def _executable(self) -> str:
        if not self._settings.executable.is_file():
            raise ToolError(f"Schemathesis not found at {self._settings.executable}; see AGENTS.md")
        return str(self._settings.executable)

    def version(self) -> str:
        return capture([self._executable(), "--version"]).rsplit(" ", 1)[-1]

    def command(self, context: ToolRunContext) -> list[str]:
        report_dir = context.output_dir / "reports"
        argv = [
            self._executable(),
            "run",
            context.openapi_url,
            "--url",
            context.base_url + context.api_base_path,
            "--seed",
            str(context.seed),
            "--max-time",
            str(context.budget.max_time_seconds),
            "--request-timeout",
            str(context.budget.request_timeout_seconds),
            "--wait-for-schema",
            "30",
            "--report",
            ",".join(REPORT_FORMATS),
            "--report-dir",
            str(report_dir),
        ]
        for name, value in sorted(context.headers.items()):
            argv += ["--header", f"{name}: {value}"]
        return argv + list(self._settings.extra_args)

    def run(self, context: ToolRunContext) -> ToolRunResult:
        argv = self.command(context)
        context.output_dir.mkdir(parents=True, exist_ok=True)
        exit_code, seconds = run_command(
            argv,
            context.output_dir / "tool.log",
            timeout=context.budget.max_time_seconds + HARD_TIMEOUT_MARGIN_SECONDS,
            # Schemathesis keeps a crash cache (.schemathesis/) in its working directory and
            # replays cached crashes in later runs. Each run gets its own directory so runs
            # stay independent (no knowledge leaks between seeds).
            cwd=context.output_dir,
        )
        # 0 = no failures, 1 = failures found; anything else is a tool/usage error.
        if exit_code not in (0, 1):
            raise ToolError(f"schemathesis exited with {exit_code}; see {context.output_dir}")
        report_dir = context.output_dir / "reports"
        reports = {p.suffix.lstrip(".") or p.name: p for p in sorted(report_dir.glob("*"))}
        return ToolRunResult(
            tool=self.name,
            version=self.version(),
            command=tuple(argv),
            exit_code=exit_code,
            wall_seconds=round(seconds, 3),
            reports=reports,
        )


def report_paths(output_dir: Path) -> list[Path]:
    return sorted((output_dir / "reports").glob("*"))
