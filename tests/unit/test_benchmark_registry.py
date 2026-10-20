import zipfile
from pathlib import Path

import pytest

from restgen.benchmark.models import Category, CoverageKind, LaunchKind, Role, SuiteKind
from restgen.benchmark.registry import BenchmarkRegistry
from restgen.benchmark.service import ServiceEnvironment, ServiceProcess
from restgen.config import ToolchainSettings
from restgen.errors import BenchmarkError, ConfigError

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40

VALID = f"""
[suite.demo]
kind = "services"
repository = "https://example.org/demo.git"
commit = "{SHA}"
license = "MIT"
reference = "key2026"

[suite.specs]
kind = "specs"
repository = "https://example.org/specs.git"
commit = "{SHA}"
license = "none"
reference = "key2025"

[service.api]
suite = "demo"
language = "python"
framework = "fastapi"
category = "real"
role = "evaluation"
openapi = "/openapi.json"
health = "/health"
headers = {{ Authorization = "Bearer t" }}

[service.api.launch]
kind = "command"
workdir = "app"
argv = ["{{python}}", "-m", "uvicorn", "main:app", "--port", "{{port}}"]

[service.api.coverage]
kind = "coveragepy"
include = ["src", "lib"]
"""


def _registry(tmp_path: Path, text: str) -> BenchmarkRegistry:
    manifest = tmp_path / "benchmark.toml"
    manifest.write_text(text)
    return BenchmarkRegistry.load(manifest)


def test_repository_manifest_loads() -> None:
    registry = BenchmarkRegistry.load(ROOT / "configs" / "benchmark.toml")
    assert {"restgym", "wfd", "wafp", "restestbench", "prab"} <= set(registry.suites)
    booking = registry.service("booking")
    assert booking.category is Category.ARTIFICIAL
    assert booking.role is Role.DEVELOPMENT


def test_valid_manifest(tmp_path: Path) -> None:
    registry = _registry(tmp_path, VALID)
    assert registry.suite("specs").kind is SuiteKind.SPECS
    service = registry.service("api")
    assert service.launch.kind is LaunchKind.COMMAND
    assert service.coverage.kind is CoverageKind.COVERAGEPY
    assert service.headers == {"Authorization": "Bearer t"}
    assert [s.name for s in registry.services_of("demo")] == ["api"]
    with pytest.raises(ConfigError):
        registry.service("nope")
    with pytest.raises(ConfigError):
        registry.suite("nope")


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (f'commit = "{SHA}"', 'commit = "main"', "40-character"),
        ('suite = "demo"', 'suite = "ghost"', "unknown suite"),
        ('suite = "demo"', 'suite = "specs"', "has no services"),
        ('role = "evaluation"', 'role = "testing"', "role must be one of"),
        ('"--port", "{port}"', '"--port", "8000"', "port"),
        ('health = "/health"', 'health = "health"', "URL path"),
    ],
)
def test_invalid_manifests(tmp_path: Path, old: str, new: str, message: str) -> None:
    assert old in VALID
    with pytest.raises(ConfigError, match=message):
        _registry(tmp_path, VALID.replace(old, new, 1))


def test_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        BenchmarkRegistry.load(tmp_path / "none.toml")


def test_service_argv_wraps_python_in_coverage(tmp_path: Path) -> None:
    service = _registry(tmp_path, VALID).service("api")
    environment = ServiceEnvironment(service, tmp_path / "bench")
    plain = ServiceProcess(service, environment, tmp_path / "suite", tmp_path / "log", port=8123)
    assert plain.argv() == [str(environment.python), "-m", "uvicorn", "main:app", "--port", "8123"]
    assert plain.base_url == "http://127.0.0.1:8123"

    data = tmp_path / "cov" / ".coverage"
    covered = ServiceProcess(
        service, environment, tmp_path / "suite", tmp_path / "log", tmp_path / "cov", 9
    )
    argv = covered.argv()
    assert argv[:4] == [str(environment.python), "-m", "coverage", "run"]
    assert f"--data-file={data.resolve()}" in argv
    assert "--source=src,lib" in argv
    assert argv[-5:] == ["-m", "uvicorn", "main:app", "--port", "9"]

    with pytest.raises(BenchmarkError, match="not installed"):
        plain.start()


JVM = f"""
[suite.wfd]
kind = "services"
repository = "https://example.org/wfd.git"
commit = "{SHA}"
license = "Apache-2.0"
reference = "k"

[service.svc]
suite = "wfd"
language = "java"
framework = "spring-boot"
category = "real"
role = "unassigned"
openapi = "file:openapi/svc.json"
health = "/"
health_any_status = true

[service.svc.launch]
kind = "jvm"
jdk = "8"
jar = "build/svc-sut.jar"
jvm_args = ["-Dserver.port={{port}}", "-Xmx1G"]
args = ["--flag"]
build_root = "build"
build_module = "svc"

[service.svc.coverage]
kind = "jacoco"
agent = "jacoco/agent.jar"
cli = "jacoco/cli.jar"
classes = ["build/svc-sut.jar"]
include = ["org/svc"]
"""


def test_jvm_service_runs_jar_with_jacoco_agent(tmp_path: Path) -> None:
    service = _registry(tmp_path, JVM).service("svc")
    assert service.launch.kind is LaunchKind.JVM
    assert service.health_any_status
    toolchain = ToolchainSettings({"8": tmp_path / "jdk8"}, tmp_path / "mvn", tmp_path / "m2")
    suite = tmp_path / "suite"
    environment = ServiceEnvironment(service, tmp_path / "bench", suite, toolchain)
    assert not environment.ready  # jar not built yet
    (suite / "build").mkdir(parents=True)
    (suite / "build" / "svc-sut.jar").write_bytes(b"jar")
    assert environment.ready

    process = ServiceProcess(service, environment, suite, tmp_path / "log", tmp_path / "cov", 7000)
    argv = process.argv()
    assert argv[0] == str(tmp_path / "jdk8" / "bin" / "java")
    assert argv[1] == (
        f"-javaagent:{suite.resolve() / 'jacoco/agent.jar'}="
        f"destfile={(tmp_path / 'cov' / 'jacoco.exec').resolve()},append=false,dumponexit=true"
    )
    assert argv[2:] == [
        "-Dserver.port=7000",
        "-Xmx1G",
        "-jar",
        str((suite / "build" / "svc-sut.jar").resolve()),
        "--flag",
    ]


def test_own_classes_are_extracted_from_a_fat_jar(tmp_path: Path) -> None:
    service = _registry(tmp_path, JVM).service("svc")
    suite = tmp_path / "suite"
    (suite / "build").mkdir(parents=True)
    jar = suite / "build" / "svc-sut.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("BOOT-INF/classes/org/svc/App.class", b"own")
        archive.writestr("BOOT-INF/classes/application.yml", b"config")
        archive.writestr("BOOT-INF/lib/spring.jar", b"library")
        archive.writestr("org/svcx/Other.class", b"not ours")
    toolchain = ToolchainSettings({"8": tmp_path}, tmp_path, tmp_path)
    environment = ServiceEnvironment(service, tmp_path / "bench", suite, toolchain)
    process = ServiceProcess(service, environment, suite, tmp_path / "log", tmp_path / "cov")
    classes = process._own_classes(jar)
    found = sorted(p.relative_to(classes).as_posix() for p in classes.rglob("*") if p.is_file())
    assert found == ["org/svc/App.class"]


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('jar = "build/svc-sut.jar"\n', "", "needs jdk and jar"),
        ('jvm_args = ["-Dserver.port={port}", "-Xmx1G"]', "jvm_args = []", "port"),
        ('cli = "jacoco/cli.jar"\n', "", "agent, cli and classes"),
        ("health_any_status = true", 'health_any_status = "yes"', "true or false"),
    ],
)
def test_invalid_jvm_services(tmp_path: Path, old: str, new: str, message: str) -> None:
    assert old in JVM
    with pytest.raises(ConfigError, match=message):
        _registry(tmp_path, JVM.replace(old, new, 1))
