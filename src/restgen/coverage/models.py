"""Tool-independent code coverage with the covered element sets kept for set algebra."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from restgen.errors import MeasurementError


def ratio(covered: int, total: int) -> float | None:
    """covered/total, or None when nothing is measurable (never a fake 0 or 1)."""
    return covered / total if total > 0 else None


@dataclass(frozen=True)
class CodeCoverage:
    """Element ids look like ``path:line`` (lines), ``path:from->to`` or ``path:line#k``
    (branches) and ``path:qualified-name`` (methods); see the readers for details."""

    tool: str
    covered_lines: frozenset[str]
    total_lines: int
    covered_branches: frozenset[str]
    total_branches: int
    covered_methods: frozenset[str] | None = None
    total_methods: int | None = None

    def __post_init__(self) -> None:
        if len(self.covered_lines) > self.total_lines:
            raise MeasurementError("more covered lines than lines")
        if len(self.covered_branches) > self.total_branches:
            raise MeasurementError("more covered branches than branches")
        if (self.covered_methods is None) != (self.total_methods is None):
            raise MeasurementError("method coverage needs both covered set and total")

    @property
    def line_ratio(self) -> float | None:
        return ratio(len(self.covered_lines), self.total_lines)

    @property
    def branch_ratio(self) -> float | None:
        return ratio(len(self.covered_branches), self.total_branches)

    @property
    def method_ratio(self) -> float | None:
        if self.covered_methods is None or self.total_methods is None:
            return None
        return ratio(len(self.covered_methods), self.total_methods)

    def summary(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "lines_covered": len(self.covered_lines),
            "lines_total": self.total_lines,
            "line_coverage": self.line_ratio,
            "branches_covered": len(self.covered_branches),
            "branches_total": self.total_branches,
            "branch_coverage": self.branch_ratio,
            "methods_covered": None if self.covered_methods is None else len(self.covered_methods),
            "methods_total": self.total_methods,
            "method_coverage": self.method_ratio,
        }

    def to_record(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "covered_lines": sorted(self.covered_lines),
            "total_lines": self.total_lines,
            "covered_branches": sorted(self.covered_branches),
            "total_branches": self.total_branches,
            "covered_methods": None
            if self.covered_methods is None
            else sorted(self.covered_methods),
            "total_methods": self.total_methods,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> CodeCoverage:
        methods = record.get("covered_methods")
        try:
            return cls(
                tool=str(record["tool"]),
                covered_lines=frozenset(record["covered_lines"]),
                total_lines=int(record["total_lines"]),
                covered_branches=frozenset(record["covered_branches"]),
                total_branches=int(record["total_branches"]),
                covered_methods=None if methods is None else frozenset(methods),
                total_methods=None
                if record.get("total_methods") is None
                else int(record["total_methods"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MeasurementError(f"malformed coverage record: {exc}") from exc
