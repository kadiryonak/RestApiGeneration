from pathlib import Path

import pytest

from restgen.benchmark.models import Category, CoverageKind, LaunchKind, Role, SuiteKind
from restgen.benchmark.registry import BenchmarkRegistry
from restgen.benchmark.service import ServiceEnvironment, ServiceProcess
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

    data = tmp_path / ".coverage"
    covered = ServiceProcess(service, environment, tmp_path / "suite", tmp_path / "log", data, 9)
    argv = covered.argv()
    assert argv[:4] == [str(environment.python), "-m", "coverage", "run"]
    assert f"--data-file={data.resolve()}" in argv
    assert "--source=src,lib" in argv
    assert argv[-5:] == ["-m", "uvicorn", "main:app", "--port", "9"]

    with pytest.raises(BenchmarkError, match="not installed"):
        plain.start()
