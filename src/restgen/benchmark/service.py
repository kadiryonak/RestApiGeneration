"""Install, start, health-check and stop a service under test, optionally under coverage.

* ``command`` services (Python) run in their own venv, under coverage.py;
* ``jvm`` services (WFD/EMB) are built once with the pinned Maven + JDK and run with the
  JaCoCo agent, exactly as WFD's own Dockerfiles start them, minus Docker. JaCoCo writes
  its execution data on JVM shutdown (``dumponexit``), which a normal SIGINT triggers.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import time
import zipfile
from pathlib import Path
from types import TracebackType

import httpx

from restgen.benchmark.fetcher import checkout
from restgen.benchmark.models import CoverageKind, LaunchKind, Service
from restgen.config import ToolchainSettings
from restgen.coverage.models import CodeCoverage
from restgen.coverage.readers import CoveragePyReader, JacocoXmlReader
from restgen.errors import BenchmarkError, MeasurementError

SERVICE_PYTHON = "3.12"
COVERAGE_REQUIREMENT = "coverage==7.16.2"
STARTUP_TIMEOUT_SECONDS = 180.0  # Spring Boot services take a while to start
SHUTDOWN_TIMEOUT_SECONDS = 30.0
COVERAGE_DATA = {CoverageKind.COVERAGEPY: ".coverage", CoverageKind.JACOCO: "jacoco.exec"}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


class ServiceEnvironment:
    """What a service needs before it can start.

    command: a venv in ``<benchmark_dir>/services/<name>/.venv``;
    jvm: the service jar inside the suite checkout, built with Maven if missing.
    """

    def __init__(
        self,
        service: Service,
        benchmark_dir: Path,
        suite_path: Path | None = None,
        toolchain: ToolchainSettings | None = None,
    ) -> None:
        self.service = service
        self.root = benchmark_dir / "services" / service.name
        self.venv = self.root / ".venv"
        self.suite_path = suite_path
        self.toolchain = toolchain

    @property
    def python(self) -> Path:
        return self.venv / "bin" / "python"

    @property
    def source(self) -> Path:
        """Checkout of the service's own repository (when it is not in the suite)."""
        return self.root / "src"

    @property
    def code_root(self) -> Path:
        """Directory ``launch.workdir`` is relative to."""
        if self.service.launch.source_repository:
            return self.source
        if self.suite_path is None:
            raise BenchmarkError(f"service {self.service.name}: suite checkout unknown")
        return self.suite_path

    @property
    def java(self) -> Path:
        if self.toolchain is None or self.service.launch.jdk not in self.toolchain.jdks:
            raise BenchmarkError(
                f"service {self.service.name}: no JDK {self.service.launch.jdk!r} in [toolchain]"
            )
        return self.toolchain.jdks[self.service.launch.jdk] / "bin" / "java"

    def suite_file(self, relative: str) -> Path:
        if self.suite_path is None:
            raise BenchmarkError(f"service {self.service.name}: suite checkout unknown")
        return (self.suite_path / relative).resolve()

    @property
    def jar(self) -> Path:
        return self.suite_file(self.service.launch.jar)

    @property
    def ready(self) -> bool:
        kind = self.service.launch.kind
        if kind is LaunchKind.COMMAND:
            return self.python.is_file()
        if kind is LaunchKind.JVM:
            return self.suite_path is not None and self.jar.is_file()
        return False

    def setup(self) -> None:
        kind = self.service.launch.kind
        if kind is LaunchKind.COMMAND:
            self._setup_python()
        elif kind is LaunchKind.JVM:
            self._setup_jvm()
        else:
            raise BenchmarkError(
                f"service {self.service.name}: launch kind {kind.value!r} is not supported yet"
            )

    def _setup_python(self) -> None:
        launch = self.service.launch
        self.root.mkdir(parents=True, exist_ok=True)
        if launch.source_repository:
            checkout(launch.source_repository, launch.source_commit, self.source)
            for relative, line in launch.append_lines.items():
                with (self.source / relative).open("a", encoding="utf-8") as handle:
                    handle.write("\n" + line + "\n")
        python = launch.python or SERVICE_PYTHON
        uv_env = dict(os.environ)
        if self.toolchain is not None:
            uv_env.update(UV_PYTHON_INSTALL_DIR=str(self.toolchain.python_dir),
                          UV_PYTHON_DOWNLOADS="automatic")
        _run(["uv", "venv", "--python", python, "--allow-existing", str(self.venv)], env=uv_env)
        install = ["uv", "pip", "install", "--python", str(self.python)]
        for index, requirements in enumerate(launch.requirements_files):
            path = self.suite_file(requirements)
            if launch.skip_requirements:
                path = self._filtered(path, self.root / f"requirements-{index}.txt")
            _run([*install, "-r", str(path)])
        packages = list(launch.requirements)
        if self.service.coverage.kind is CoverageKind.COVERAGEPY:
            packages.append(self.service.coverage.requirement or COVERAGE_REQUIREMENT)
        if packages:
            _run([*install, *packages])
        if launch.install_source:
            _run([*install, str(self.code_root)])

    def _filtered(self, source: Path, target: Path) -> Path:
        skip = {name.lower().replace("_", "-") for name in self.service.launch.skip_requirements}
        kept = []
        for line in source.read_text(encoding="utf-8").splitlines():
            name = re.split(r"[\s=<>!~;\[]", line.strip(), maxsplit=1)[0]
            if name.lower().replace("_", "-") not in skip:
                kept.append(line)
        target.write_text("\n".join(kept) + "\n", encoding="utf-8")
        return target

    def _setup_jvm(self) -> None:
        if self.jar.is_file():
            return
        launch = self.service.launch
        if not (launch.build_root and launch.build_module):
            raise BenchmarkError(f"service {self.service.name}: jar missing and no build given")
        if self.toolchain is None:
            raise BenchmarkError("JVM services need the [toolchain] settings")
        java_home = self.java.parent.parent
        _run(
            [
                str(self.toolchain.maven / "bin" / "mvn"),
                "-B",
                "-q",
                f"-Dmaven.repo.local={self.toolchain.maven_repo}",
                "-DskipTests",
                "install",
                "-am",
                "-pl",
                launch.build_module,
            ],
            cwd=self.suite_file(launch.build_root),
            env={**os.environ, "JAVA_HOME": str(java_home),
                 "PATH": f"{java_home / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"},
            timeout=3600,
        )
        if not self.jar.is_file():
            raise BenchmarkError(f"build finished but {self.jar} does not exist")


class ServiceProcess:
    """A running instance. ``coverage_dir`` enables coverage collection into that folder."""

    def __init__(
        self,
        service: Service,
        environment: ServiceEnvironment,
        suite_path: Path,
        log_path: Path,
        coverage_dir: Path | None = None,
        port: int | None = None,
    ) -> None:
        if service.launch.kind not in (LaunchKind.COMMAND, LaunchKind.JVM):
            raise BenchmarkError(
                f"service {service.name}: launch kind {service.launch.kind.value!r} "
                "is not supported yet"
            )
        if coverage_dir is not None and service.coverage.kind is CoverageKind.NONE:
            raise BenchmarkError(f"service {service.name}: no coverage collection configured")
        self.service = service
        self.environment = environment
        self.suite_path = suite_path.resolve()
        base = environment.code_root if service.launch.source_repository else suite_path
        self.workdir = (base / service.launch.workdir).resolve()
        self.log_path = log_path
        self.coverage_data = (
            (coverage_dir / COVERAGE_DATA[service.coverage.kind]).resolve()
            if coverage_dir is not None
            else None
        )
        self.port = port or free_port()
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _sub(self, arg: str) -> str:
        return arg.replace("{port}", str(self.port))

    def argv(self) -> list[str]:
        if self.service.launch.kind is LaunchKind.JVM:
            return self._jvm_argv()
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
                argv.append(self._sub(arg))
        return argv

    def _jvm_argv(self) -> list[str]:
        launch = self.service.launch
        argv = [str(self.environment.java)]
        if self.coverage_data is not None:
            agent = self.suite_path / self.service.coverage.agent
            argv.append(
                f"-javaagent:{agent}=destfile={self.coverage_data},append=false,dumponexit=true"
            )
        argv += [self._sub(a) for a in launch.jvm_args]
        argv += ["-jar", str(self.environment.jar)]
        argv += [self._sub(a) for a in launch.args]
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
            self.coverage_data.parent.mkdir(parents=True, exist_ok=True)
            self.coverage_data.unlink(missing_ok=True)
        self._reset_state()
        launch_env = {k: self._sub(v) for k, v in self.service.launch.env.items()}
        env = {**os.environ, **launch_env, "PYTHONUNBUFFERED": "1"}
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

    def _reset_state(self) -> None:
        paths = self.service.launch.reset_paths
        if not paths:
            return
        if not self.service.launch.source_repository:
            raise BenchmarkError(f"service {self.service.name}: reset_paths needs a source checkout")
        _run(["git", "checkout", "--", *paths], cwd=self.environment.source)

    def stop(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        # SIGINT: a normal shutdown, so coverage.py / JaCoCo write their data.
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

    def export_coverage(self) -> CodeCoverage:
        """After ``stop()``: turn the raw coverage data into a report next to it and read it."""
        data = self.coverage_data
        if data is None or not data.is_file():
            raise MeasurementError(f"no coverage data was written for {self.service.name}")
        if self.service.coverage.kind is CoverageKind.JACOCO:
            report = data.parent / "coverage.xml"
            argv = [str(self.environment.java), "-jar",
                    str(self.suite_path / self.service.coverage.cli), "report", str(data)]
            for classes in self.service.coverage.classes:
                argv += ["--classfiles", str(self._own_classes(self.suite_path / classes))]
            _run([*argv, "--xml", str(report)])
            return JacocoXmlReader(self.service.coverage.include).read(report)
        report = data.parent / "coverage.json"
        _run(
            [str(self.environment.python), "-m", "coverage", "json",
             f"--data-file={data}", "-o", str(report)],
            cwd=self.workdir,
        )
        return CoveragePyReader(source_root=self.workdir).read(report)

    def _own_classes(self, source: Path) -> Path:
        """A directory or jar of classes, reduced to the service's own packages.

        A Spring Boot fat jar nests every library jar; JaCoCo refuses to analyse it
        ("Can't add different class with same name") and the libraries are not part of
        the measured code anyway. Own classes are extracted once into the service's
        environment folder (from ``BOOT-INF/classes/`` or the jar root)."""
        if source.is_dir() or not zipfile.is_zipfile(source):
            return source
        target = self.environment.root / "classes" / source.stem
        if target.is_dir():
            return target
        prefixes = tuple(p.strip("/") + "/" for p in self.service.coverage.include)
        with zipfile.ZipFile(source) as jar:
            for entry in jar.namelist():
                name = entry.removeprefix("BOOT-INF/classes/")
                if name.endswith(".class") and (not prefixes or name.startswith(prefixes)):
                    destination = target / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(jar.read(entry))
        if not target.is_dir():
            raise MeasurementError(f"no classes of {prefixes} found in {source}")
        return target

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
                response = httpx.get(url, headers=dict(self.service.headers), timeout=2.0)
                if response.is_success or self.service.health_any_status:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        self.stop()
        raise BenchmarkError(f"service {self.service.name} not healthy at {url}")


def _run(
    argv: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 1800,
) -> None:
    try:
        result = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BenchmarkError(f"{argv[0]} failed: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr.strip() or result.stdout.strip())[-2000:]
        raise BenchmarkError(f"{' '.join(argv[:4])} failed: {detail}")
