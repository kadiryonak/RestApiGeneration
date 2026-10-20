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
    JVM = "jvm"  # a jar run by a pinned JDK (WFD/EMB services), built with Maven on setup
    CONTAINER = "container"  # Docker/Podman image (RESTgym); runtime not implemented yet


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
    # JVM: java from toolchain.jdks[jdk]; jar/build paths are relative to the suite
    # checkout; {port} is substituted in jvm_args and args.
    jdk: str = ""
    jar: str = ""
    jvm_args: tuple[str, ...] = ()
    args: tuple[str, ...] = ()
    build_root: str = ""  # Maven reactor directory, e.g. jdk_8_maven
    build_module: str = ""  # module (relative to build_root) whose jar is ``jar``


@dataclass(frozen=True)
class CoverageSpec:
    kind: CoverageKind
    # coveragepy: --source entries relative to workdir; jacoco: package prefixes (org/foo)
    include: tuple[str, ...] = ()
    # jacoco (paths relative to the suite checkout): agent and CLI jars, and the compiled
    # classes of the service itself (not its libraries) the report is built from
    agent: str = ""
    cli: str = ""
    classes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Service:
    name: str
    suite: str
    language: str
    framework: str
    category: Category
    role: Role
    openapi: str  # URL path on the running service ("/openapi.json") or "file:<path in suite>"
    health: str  # URL path that answers once the service is ready
    launch: Launch
    coverage: CoverageSpec
    headers: Mapping[str, str] = field(default_factory=dict)  # e.g. a fixed auth token
    notes: str = ""
    # True: any HTTP answer means "up" (APIs without an unauthenticated 2xx endpoint)
    health_any_status: bool = False

    @property
    def openapi_is_file(self) -> bool:
        return self.openapi.startswith("file:")
