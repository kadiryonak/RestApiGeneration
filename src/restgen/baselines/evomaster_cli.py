"""EvoMaster (black-box) as a search-based baseline.

EvoMaster evolves test suites with its own search algorithm (MIO/SMARTS family) and
writes them as Python ``unittest`` files, so its output is a persistent suite measured
exactly like the Hypothesis suite and the method's output. The generated tests hard-code
the base URL they were generated against (the run's proxy); the runner therefore re-runs
them behind a proxy on the same port.

Transport note: uvicorn closes the connection after an unhandled exception (500), and
EvoMaster's pooled HTTP client crashes on the reset connection when it talks to such a
service directly. Through the recording proxy the tool-facing connection stays open, so
this never reaches the tool; it is the same proxy every tool goes through.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from restgen.baselines.base import (
    PytestSuiteTool,
    ToolRunContext,
    ToolRunResult,
    run_command,
)
from restgen.config import EvoMasterSettings
from restgen.errors import ToolError

# Grace period on top of --maxTime for startup, minimisation and writing the tests.
HARD_TIMEOUT_MARGIN_SECONDS = 600


class EvoMasterCli(PytestSuiteTool):
    name = "evomaster"

    def __init__(self, settings: EvoMasterSettings) -> None:
        self._settings = settings

    @property
    def python(self) -> Path:
        return self._settings.python

    def _jar(self) -> Path:
        if not self._settings.jar.is_file():
            raise ToolError(f"EvoMaster jar not found at {self._settings.jar}; run `make tools`")
        return self._settings.jar

    def version(self) -> str:
        jar = self._jar()
        digest = hashlib.sha256(jar.read_bytes()).hexdigest()
        return f"{jar.parent.name} (evomaster.jar sha256 {digest[:16]})"

    def command(self, context: ToolRunContext) -> list[str]:
        out = context.output_dir
        argv = [
            self._settings.java,
            "-jar",
            str(self._jar()),
            "--blackBox",
            "true",
            "--schema",
            context.openapi_url,
            "--base",
            context.base_url,
            "--maxTime",
            f"{context.budget.max_time_seconds}s",
            "--seed",
            str(context.seed),
            "--outputFormat",
            "PYTHON_UNITTEST",
            "--outputFolder",
            str(out / "suite"),
            "--writeStatistics",
            "true",
            "--statisticsFile",
            str(out / "reports" / "statistics.csv"),
            "--showProgress",
            "false",
        ]
        # EvoMaster supports a fixed number of header slots (header0, header1, header2).
        for index, (name, value) in enumerate(sorted(context.headers.items())):
            if index > 2:
                raise ToolError("EvoMaster accepts at most 3 fixed headers")
            argv += [f"--header{index}", f"{name}: {value}"]
        return argv + list(self._settings.extra_args)

    def run(self, context: ToolRunContext) -> ToolRunResult:
        argv = self.command(context)
        context.output_dir.mkdir(parents=True, exist_ok=True)
        exit_code, seconds = run_command(
            argv,
            context.output_dir / "tool.log",
            timeout=context.budget.max_time_seconds + HARD_TIMEOUT_MARGIN_SECONDS,
            cwd=context.output_dir,  # EvoMaster writes em.yaml / process_data to its cwd
        )
        if exit_code != 0:
            raise ToolError(f"EvoMaster exited with {exit_code}; see {context.output_dir}")
        tests = generated_test_modules(context.output_dir / "suite")
        if not tests:
            raise ToolError(f"EvoMaster wrote no test module; see {context.output_dir}")
        # The suite is not executed here: that would add traffic to the exploration
        # recording. Its reference run is the first clean re-execution (output/rerun-1).
        return ToolRunResult(
            tool=self.name,
            version=self.version(),
            command=tuple(argv),
            exit_code=exit_code,
            wall_seconds=round(seconds, 3),
            tests=tuple(tests),
            reports={"statistics": context.output_dir / "reports" / "statistics.csv"},
        )


def generated_test_modules(folder: Path) -> list[Path]:
    """Generated files that define unittest test cases (helpers are left out)."""
    if not folder.is_dir():
        return []
    return sorted(
        path
        for path in folder.glob("*.py")
        if "unittest.TestCase" in path.read_text(encoding="utf-8", errors="replace")
    )
