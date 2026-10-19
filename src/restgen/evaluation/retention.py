"""Exploration coverage vs. output coverage (analysis §5.4).

* exploration coverage: everything reached by all calls made while the tool was running;
* output coverage: what the *saved* test suite reaches when re-run alone on a clean
  service with the generator (and any LLM) switched off.

retention = |B_exploration ∩ B_rerun| / |B_exploration|, None when B_exploration is empty.
This ratio is our own proposal, not an established metric in the literature.
"""

from __future__ import annotations

from collections.abc import Set
from dataclasses import dataclass
from typing import Any

from restgen.coverage.models import CodeCoverage, ratio


def retention(exploration: Set[str], rerun: Set[str]) -> float | None:
    return ratio(len(exploration & rerun), len(exploration))


@dataclass(frozen=True)
class CoverageRetention:
    exploration: CodeCoverage
    output: CodeCoverage

    @property
    def line_retention(self) -> float | None:
        return retention(self.exploration.covered_lines, self.output.covered_lines)

    @property
    def branch_retention(self) -> float | None:
        return retention(self.exploration.covered_branches, self.output.covered_branches)

    def summary(self) -> dict[str, Any]:
        return {
            "line_retention": self.line_retention,
            "branch_retention": self.branch_retention,
            # reached only by the saved suite (e.g. a rerun path the exploration missed)
            "lines_only_in_output": len(self.output.covered_lines - self.exploration.covered_lines),
        }
