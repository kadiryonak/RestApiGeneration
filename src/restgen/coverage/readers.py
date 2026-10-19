"""Readers that turn a coverage tool's report into :class:`CodeCoverage`.

* coverage.py JSON (``coverage json``) for Python services: branches are arcs
  ``from->to``, methods are the ``functions`` regions (coverage >= 7.5).
* JaCoCo XML for JVM services (RESTgym, EMB): JaCoCo reports *how many* branches of a line
  were taken, not which ones, so branch ids are ``line#k`` for k < covered. Set operations
  on JaCoCo branches are therefore count-based per line.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from restgen.coverage.models import CodeCoverage
from restgen.errors import MeasurementError


class CoverageReader(ABC):
    tool: str

    @abstractmethod
    def read(self, report: Path) -> CodeCoverage: ...


class CoveragePyReader(CoverageReader):
    """``source_root`` makes file ids relative (stable across machines and runs)."""

    tool = "coveragepy"

    def __init__(self, source_root: Path | None = None) -> None:
        self._root = source_root.resolve() if source_root else None

    def read(self, report: Path) -> CodeCoverage:
        data = _load_json(report)
        files = data.get("files")
        if not isinstance(files, dict):
            raise MeasurementError(f"{report}: not a coverage.py JSON report")
        covered_lines: set[str] = set()
        covered_branches: set[str] = set()
        covered_methods: set[str] = set()
        total_lines = total_branches = total_methods = 0
        has_functions = False
        for raw_name, entry in files.items():
            name = self._relative(raw_name)
            executed = set(entry.get("executed_lines", []))
            missing = set(entry.get("missing_lines", []))
            total_lines += len(executed | missing)
            covered_lines.update(f"{name}:{line}" for line in executed)
            taken = [tuple(arc) for arc in entry.get("executed_branches", [])]
            not_taken = entry.get("missing_branches", [])
            total_branches += len(taken) + len(not_taken)
            covered_branches.update(f"{name}:{a}->{b}" for a, b in taken)
            functions = entry.get("functions")
            if isinstance(functions, dict):
                has_functions = True
                for qualname, region in functions.items():
                    if not qualname:  # the module-level pseudo region
                        continue
                    total_methods += 1
                    if region.get("executed_lines"):
                        covered_methods.add(f"{name}:{qualname}")
        return CodeCoverage(
            tool=self.tool,
            covered_lines=frozenset(covered_lines),
            total_lines=total_lines,
            covered_branches=frozenset(covered_branches),
            total_branches=total_branches,
            covered_methods=frozenset(covered_methods) if has_functions else None,
            total_methods=total_methods if has_functions else None,
        )

    def _relative(self, name: str) -> str:
        path = Path(name)
        if self._root and path.is_absolute():
            try:
                return path.resolve().relative_to(self._root).as_posix()
            except ValueError:
                return path.as_posix()
        return path.as_posix()


class JacocoXmlReader(CoverageReader):
    """``include_packages``: slash-separated package prefixes (e.g. ``org/foo``) that belong
    to the service; everything else (third-party code) is ignored. Empty = keep all."""

    tool = "jacoco"

    def __init__(self, include_packages: Sequence[str] = ()) -> None:
        self._include = tuple(p.strip("/") for p in include_packages)

    def read(self, report: Path) -> CodeCoverage:
        try:
            root = ET.parse(report).getroot()
        except (OSError, ET.ParseError) as exc:
            raise MeasurementError(f"cannot read JaCoCo XML {report}: {exc}") from exc
        if root.tag != "report":
            raise MeasurementError(f"{report}: not a JaCoCo XML report")
        covered_lines: set[str] = set()
        covered_branches: set[str] = set()
        covered_methods: set[str] = set()
        total_lines = total_branches = total_methods = 0
        for package in root.iter("package"):
            package_name = package.get("name", "")
            if not self._included(package_name):
                continue
            for sourcefile in package.iter("sourcefile"):
                prefix = f"{package_name}/{sourcefile.get('name', '')}".lstrip("/")
                for line in sourcefile.iter("line"):
                    number = line.get("nr")
                    mi, ci = _int(line, "mi"), _int(line, "ci")
                    mb, cb = _int(line, "mb"), _int(line, "cb")
                    if mi + ci > 0:
                        total_lines += 1
                        if ci > 0:
                            covered_lines.add(f"{prefix}:{number}")
                    total_branches += mb + cb
                    covered_branches.update(f"{prefix}:{number}#{k}" for k in range(cb))
            for cls in package.iter("class"):
                class_name = cls.get("name", "")
                for method in cls.iter("method"):
                    counter = _counter(method, "METHOD")
                    if counter is None:
                        continue
                    total_methods += 1
                    if counter[1] > 0:
                        covered_methods.add(
                            f"{class_name}:{method.get('name', '')}{method.get('desc', '')}"
                        )
        return CodeCoverage(
            tool=self.tool,
            covered_lines=frozenset(covered_lines),
            total_lines=total_lines,
            covered_branches=frozenset(covered_branches),
            total_branches=total_branches,
            covered_methods=frozenset(covered_methods),
            total_methods=total_methods,
        )

    def _included(self, package: str) -> bool:
        return not self._include or any(
            package == p or package.startswith(p + "/") for p in self._include
        )


def _int(element: ET.Element, attribute: str) -> int:
    return int(element.get(attribute, "0"))


def _counter(element: ET.Element, kind: str) -> tuple[int, int] | None:
    for counter in element.findall("counter"):
        if counter.get("type") == kind:
            return _int(counter, "missed"), _int(counter, "covered")
    return None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MeasurementError(f"cannot read coverage report {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise MeasurementError(f"{path}: coverage report must be an object")
    return data
