"""Install, start, health-check and stop a service under test, optionally under coverage."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from types import TracebackType

import httpx

from restgen.benchmark.models import CoverageKind, LaunchKind, Service
from restgen.coverage.models import CodeCoverage
from restgen.coverage.readers import CoveragePyReader
from restgen.errors import BenchmarkError, MeasurementError

SERVICE_PYTHON = "3.12"
COVERAGE_REQUIREMENT = "coverage==7.16.2"
STARTUP_TIMEOUT_SECONDS = 60.0
SHUTDOWN_TIMEOUT_SECONDS = 20.0


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


class ServiceEnvironment:
    """The service's own virtualenv: ``<benchmark_dir>/services/<name>/.venv``."""

    def __init__(self, service: Service, benchmark_dir: Path) -> None:
        self.service = service
        self.root = benchmark_dir / "services" / service.name
        self.venv = self.root / ".venv"

    @property
    def python(self) -> Path:
        return self.venv / "bin" / "python"

    @property
    def ready(self) -> bool:
        return self.python.is_file()

    def setup(self) -> None:
        if self.service.launch.kind is not LaunchKind.COMMAND:
            raise BenchmarkError(
                f"service {self.service.name}: launch kind "
                f"{self.service.launch.kind.value!r} is not supported yet"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        _run(["uv", "venv", "--python", SERVICE_PYTHON, "--allow-existing", str(self.venv)])
        packages = list(self.service.launch.requirements)
        if self.service.coverage.kind is CoverageKind.COVERAGEPY:
            packages.append(COVERAGE_REQUIREMENT)
        if packages:
            _run(["uv", "pip", "install", "--python", str(self.python), *packages])


class ServiceProcess:
    """A running instance. ``coverage_data`` enables coverage.py collection."""

    def __init__(
        self,
        service: Service,
        environment: ServiceEnvironment,
        suite_path: Path,
        log_path: Path,
        coverage_data: Path | None = None,
        port: int | None = None,
    ) -> None:
        if service.launch.kind is not LaunchKind.COMMAND:
            raise BenchmarkError(f"service {service.name}: only 'command' launch is supported")
        if coverage_data is not None and service.coverage.kind is not CoverageKind.COVERAGEPY:
            raise BenchmarkError(f"service {service.name}: no coverage.py collection configured")
        self.service = service
        self.environment = environment
        self.workdir = (suite_path / service.launch.workdir).resolve()
        self.log_path = log_path
        self.coverage_data = coverage_data.resolve() if coverage_data else None
        self.port = port or free_port()
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def argv(self) -> list[str]:
        python = [str(self.environment.python)]
        if self.coverage_data is not None:
            sources = ",".join(self.service.coverage.include) or "."
            python += [
                "-m",
                "coverage",
                "run",
                "--branch",
                f"--data-file={self.coverage_data}",
                f"--source={sources}",
            ]
        argv: list[str] = []
        for arg in self.service.launch.argv:
            if arg == "{python}":
                argv.extend(python)
            else:
                argv.append(arg.replace("{port}", str(self.port)))
        return argv

    def start(self) -> ServiceProcess:
        if not self.environment.ready:
            raise BenchmarkError(
                f"service {self.service.name} is not installed; run `restgen benchmark setup`"
            )
        if not self.workdir.is_dir():
            raise BenchmarkError(f"service working directory missing: {self.workdir}")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.coverage_data is not None:
            self.coverage_data.unlink(missing_ok=True)
        env = {**os.environ, **self.service.launch.env, "PYTHONUNBUFFERED": "1"}
        with self.log_path.open("ab") as log:
            self._process = subprocess.Popen(
                self.argv(),
                cwd=self.workdir,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._wait_until_healthy()
        return self

    def stop(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        # SIGINT lets the server shut down normally, so coverage.py writes its data file.
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()

    def __enter__(self) -> ServiceProcess:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    def export_coverage(self, report: Path) -> CodeCoverage:
        """After ``stop()``: convert the coverage.py data file to JSON and read it."""
        if self.coverage_data is None or not self.coverage_data.is_file():
            raise MeasurementError(f"no coverage data was written for {self.service.name}")
        report.parent.mkdir(parents=True, exist_ok=True)
        _run(
            [
                str(self.environment.python),
                "-m",
                "coverage",
                "json",
                f"--data-file={self.coverage_data}",
                "-o",
                str(report.resolve()),
            ],
            cwd=self.workdir,
        )
        return CoveragePyReader(source_root=self.workdir).read(report)

    def _wait_until_healthy(self) -> None:
        assert self._process is not None
        url = self.base_url + self.service.health
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise BenchmarkError(
                    f"service {self.service.name} exited during startup "
                    f"(code {self._process.returncode}); see {self.log_path}"
                )
            try:
                if httpx.get(url, headers=dict(self.service.headers), timeout=2.0).is_success:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        self.stop()
        raise BenchmarkError(f"service {self.service.name} not healthy at {url}")


def _run(argv: list[str], cwd: Path | None = None) -> None:
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BenchmarkError(f"{argv[0]} failed: {exc}") from exc
    if result.returncode != 0:
        raise BenchmarkError(f"{' '.join(argv[:4])} failed: {result.stderr.strip()[-2000:]}")
