"""Load and validate the benchmark manifest."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from restgen.benchmark.models import (
    Category,
    CoverageKind,
    CoverageSpec,
    Launch,
    LaunchKind,
    Role,
    Service,
    Suite,
    SuiteKind,
)
from restgen.errors import ConfigError

_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class BenchmarkRegistry:
    suites: Mapping[str, Suite]
    services: Mapping[str, Service]

    @classmethod
    def load(cls, manifest: Path) -> BenchmarkRegistry:
        try:
            raw = tomllib.loads(manifest.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(f"benchmark manifest not found: {manifest}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML in {manifest}: {exc}") from exc
        suites = {name: _suite(name, data) for name, data in _table(raw, "suite").items()}
        services = {name: _service(name, data) for name, data in _table(raw, "service").items()}
        for service in services.values():
            if service.suite not in suites:
                raise ConfigError(f"service {service.name}: unknown suite {service.suite!r}")
            if suites[service.suite].kind is SuiteKind.SPECS:
                raise ConfigError(f"service {service.name}: suite {service.suite} has no services")
        return cls(suites=suites, services=services)

    def suite(self, name: str) -> Suite:
        if name not in self.suites:
            raise ConfigError(f"unknown suite {name!r}; known: {', '.join(sorted(self.suites))}")
        return self.suites[name]

    def service(self, name: str) -> Service:
        if name not in self.services:
            known = ", ".join(sorted(self.services))
            raise ConfigError(f"unknown service {name!r}; known: {known}")
        return self.services[name]

    def services_of(self, suite: str) -> list[Service]:
        return [s for s in self.services.values() if s.suite == suite]


def _table(raw: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    table = raw.get(name, {})
    if not isinstance(table, Mapping) or not all(isinstance(v, Mapping) for v in table.values()):
        raise ConfigError(f"[{name}.<id>] entries must be tables")
    return table


def _str(data: Mapping[str, Any], key: str, where: str, default: str | None = None) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or (default is None and not value):
        raise ConfigError(f"{where}.{key} must be a non-empty string")
    return value


def _strs(data: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where}.{key} must be a list of strings")
    return tuple(value)


def _str_map(data: Mapping[str, Any], key: str, where: str) -> dict[str, str]:
    value = data.get(key, {})
    if not isinstance(value, Mapping) or not all(isinstance(v, str) for v in value.values()):
        raise ConfigError(f"{where}.{key} must be a table of strings")
    return dict(value)


def _enum(kind: Any, data: Mapping[str, Any], key: str, where: str) -> Any:
    value = _str(data, key, where)
    try:
        return kind(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in kind)
        raise ConfigError(f"{where}.{key} must be one of: {allowed}") from exc


def _suite(name: str, data: Mapping[str, Any]) -> Suite:
    where = f"suite.{name}"
    commit = _str(data, "commit", where)
    if not _SHA.fullmatch(commit):
        raise ConfigError(f"{where}.commit must be a full 40-character commit SHA")
    return Suite(
        name=name,
        kind=_enum(SuiteKind, data, "kind", where),
        repository=_str(data, "repository", where),
        commit=commit,
        license=_str(data, "license", where),
        reference=_str(data, "reference", where),
        notes=_str(data, "notes", where, default=""),
    )


def _service(name: str, data: Mapping[str, Any]) -> Service:
    where = f"service.{name}"
    launch_raw = data.get("launch")
    coverage_raw = data.get("coverage")
    if not isinstance(launch_raw, Mapping) or not isinstance(coverage_raw, Mapping):
        raise ConfigError(f"{where} needs [launch] and [coverage] tables")
    launch = Launch(
        kind=_enum(LaunchKind, launch_raw, "kind", f"{where}.launch"),
        argv=_strs(launch_raw, "argv", f"{where}.launch"),
        workdir=_str(launch_raw, "workdir", f"{where}.launch", default="."),
        env=_str_map(launch_raw, "env", f"{where}.launch"),
        requirements=_strs(launch_raw, "requirements", f"{where}.launch"),
        image=_str(launch_raw, "image", f"{where}.launch", default=""),
        jdk=_str(launch_raw, "jdk", f"{where}.launch", default=""),
        jar=_str(launch_raw, "jar", f"{where}.launch", default=""),
        jvm_args=_strs(launch_raw, "jvm_args", f"{where}.launch"),
        args=_strs(launch_raw, "args", f"{where}.launch"),
        build_root=_str(launch_raw, "build_root", f"{where}.launch", default=""),
        build_module=_str(launch_raw, "build_module", f"{where}.launch", default=""),
        source_repository=_str(launch_raw, "source_repository", f"{where}.launch", default=""),
        source_commit=_str(launch_raw, "source_commit", f"{where}.launch", default=""),
        python=_str(launch_raw, "python", f"{where}.launch", default=""),
        requirements_files=_strs(launch_raw, "requirements_files", f"{where}.launch"),
        skip_requirements=_strs(launch_raw, "skip_requirements", f"{where}.launch"),
        install_source=_bool(launch_raw, "install_source", f"{where}.launch"),
        reset_paths=_strs(launch_raw, "reset_paths", f"{where}.launch"),
        append_lines=_str_map(launch_raw, "append_lines", f"{where}.launch"),
    )
    if bool(launch.source_repository) != bool(launch.source_commit):
        raise ConfigError(f"{where}.launch: source_repository and source_commit go together")
    if launch.source_commit and not _SHA.fullmatch(launch.source_commit):
        raise ConfigError(f"{where}.launch.source_commit must be a full 40-character SHA")
    if launch.kind is LaunchKind.COMMAND and not launch.argv:
        raise ConfigError(f"{where}.launch.argv is required for kind 'command'")
    if launch.kind is LaunchKind.COMMAND and "{port}" not in " ".join(
        (*launch.argv, *launch.env.values())
    ):
        raise ConfigError(f"{where}.launch: argv or env must contain the {{port}} placeholder")
    if launch.kind is LaunchKind.JVM:
        if not (launch.jdk and launch.jar):
            raise ConfigError(f"{where}.launch: kind 'jvm' needs jdk and jar")
        if "{port}" not in " ".join((*launch.jvm_args, *launch.args)):
            raise ConfigError(f"{where}.launch: jvm_args or args must contain {{port}}")
    if launch.kind is LaunchKind.CONTAINER and not launch.image:
        raise ConfigError(f"{where}.launch.image is required for kind 'container'")
    for path in (_str(data, "openapi", where), _str(data, "health", where)):
        if not (path.startswith("/") or path.startswith("file:")):
            raise ConfigError(f"{where}: openapi/health must be a URL path or file:<path>")
    return Service(
        name=name,
        suite=_str(data, "suite", where),
        language=_str(data, "language", where),
        framework=_str(data, "framework", where),
        category=_enum(Category, data, "category", where),
        role=_enum(Role, data, "role", where),
        openapi=_str(data, "openapi", where),
        health=_str(data, "health", where),
        launch=launch,
        coverage=_coverage(coverage_raw, f"{where}.coverage"),
        headers=_str_map(data, "headers", where),
        notes=_str(data, "notes", where, default=""),
        health_any_status=_bool(data, "health_any_status", where),
    )


def _coverage(raw: Mapping[str, Any], where: str) -> CoverageSpec:
    spec = CoverageSpec(
        kind=_enum(CoverageKind, raw, "kind", where),
        include=_strs(raw, "include", where),
        agent=_str(raw, "agent", where, default=""),
        cli=_str(raw, "cli", where, default=""),
        classes=_strs(raw, "classes", where),
        requirement=_str(raw, "requirement", where, default=""),
    )
    if spec.kind is CoverageKind.JACOCO and not (spec.agent and spec.cli and spec.classes):
        raise ConfigError(f"{where}: kind 'jacoco' needs agent, cli and classes")
    return spec


def _bool(data: Mapping[str, Any], key: str, where: str) -> bool:
    value = data.get(key, False)
    if not isinstance(value, bool):
        raise ConfigError(f"{where}.{key} must be true or false")
    return value
