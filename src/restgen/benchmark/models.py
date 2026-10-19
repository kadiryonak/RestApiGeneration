"""Typed view of ``configs/benchmark.toml``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class SuiteKind(StrEnum):
    SERVICES = "services"  # runnable services under test
    SPECS = "specs"  # OpenAPI documents only (e.g. PRAB): schema diversity, no execution
    REQUIREMENTS = "requirements"  # services + NL requirements + mutants (RESTestBench)


class Category(StrEnum):
    REAL = "real"
    ARTIFICIAL = "artificial"  # synthetic / teaching APIs: reported separately


class Role(StrEnum):
    """Project-level split (analysis §6.2): never tune on evaluation services."""

    DEVELOPMENT = "development"
    VALIDATION = "validation"
    EVALUATION = "evaluation"
    UNASSIGNED = "unassigned"  # until docs/EXPERIMENT_PROTOCOL.md is frozen


class LaunchKind(StrEnum):
    COMMAND = "command"  # a local process started from argv
    CONTAINER = "container"  # Docker/Podman image (RESTgym, WFD); runtime not implemented yet


class CoverageKind(StrEnum):
    COVERAGEPY = "coveragepy"
    JACOCO = "jacoco"
    NONE = "none"


@dataclass(frozen=True)
class Suite:
    name: str
    kind: SuiteKind
    repository: str
    commit: str
    license: str
    reference: str  # BibTeX key in docs/literature/references.bib
    notes: str = ""


@dataclass(frozen=True)
class Launch:
    kind: LaunchKind
    # COMMAND: placeholders {python} (service venv interpreter) and {port} are substituted.
    argv: tuple[str, ...] = ()
    workdir: str = "."  # relative to the suite checkout
    env: Mapping[str, str] = field(default_factory=dict)
    requirements: tuple[str, ...] = ()  # installed into the service's own venv
    image: str = ""  # CONTAINER


@dataclass(frozen=True)
class CoverageSpec:
    kind: CoverageKind
    # coveragepy: --source entries relative to workdir; jacoco: package prefixes (org/foo)
    include: tuple[str, ...] = ()


@dataclass(frozen=True)
class Service:
    name: str
    suite: str
    language: str
    framework: str
    category: Category
    role: Role
    openapi: str  # URL path on the running service ("/openapi.json") or "file:<path in suite>"
    health: str  # URL path that answers 2xx once the service is ready
    launch: Launch
    coverage: CoverageSpec
    headers: Mapping[str, str] = field(default_factory=dict)  # e.g. a fixed auth token
    notes: str = ""

    @property
    def openapi_is_file(self) -> bool:
        return self.openapi.startswith("file:")
