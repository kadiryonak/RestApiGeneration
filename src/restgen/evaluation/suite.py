"""Quality of a *saved* Python test suite (analysis §5.1 and the stability part of §5.8).

Stages, each reported on its own because a single "success rate" hides where it fails:

* syntax valid     - the file parses as Python (file level)
* collectable      - pytest collects it as tests (file level)
* oracle reached   - the test got to its assertion: it passed, or failed *on an
                     assertion* (an exception in request setup never reached the oracle)
* passed           - passed on the reference (unmutated) service
* stable           - same outcome in every clean re-execution

Pass rate is not quality: a test with its assertions removed passes, and a correct test
fails when it finds a real bug. Report it next to the fault and mutation results.
"""

from __future__ import annotations

import ast
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from restgen.coverage.models import ratio
from restgen.errors import MeasurementError


class Outcome(StrEnum):
    PASSED = "passed"
    ASSERTION_FAILED = "assertion_failed"  # reached the oracle and it said no
    FAILED = "failed"  # any other exception inside the test body
    ERROR = "error"  # fixture/setup/collection error
    SKIPPED = "skipped"

    @property
    def reached_oracle(self) -> bool:
        return self in (Outcome.PASSED, Outcome.ASSERTION_FAILED)


@dataclass(frozen=True)
class TestResult:
    __test__ = False  # not a pytest test class

    test_id: str
    outcome: Outcome
    message: str = ""


def syntax_valid(path: Path) -> bool:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, ValueError, OSError):
        return False
    return True


def read_junit(path: Path) -> list[TestResult]:
    """Parse a pytest ``--junitxml`` report."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise MeasurementError(f"cannot read JUnit report {path}: {exc}") from exc
    results = []
    for case in root.iter("testcase"):
        test_id = f"{case.get('classname', '')}::{case.get('name', '')}".lstrip(":")
        failure, error = case.find("failure"), case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            message = failure.get("message", "") or (failure.text or "")
            outcome = Outcome.ASSERTION_FAILED if _is_assertion(failure) else Outcome.FAILED
        elif error is not None:
            message, outcome = error.get("message", "") or (error.text or ""), Outcome.ERROR
        elif skipped is not None:
            message, outcome = skipped.get("message", ""), Outcome.SKIPPED
        else:
            message, outcome = "", Outcome.PASSED
        results.append(TestResult(test_id, outcome, message[:500]))
    return results


def _is_assertion(failure: ET.Element) -> bool:
    kind = failure.get("type", "")
    message = failure.get("message", "")
    text = failure.text or ""
    if "AssertionError" in kind or message.startswith(("AssertionError", "assert ")):
        return True
    # pytest's long report ends with "E   AssertionError: ..." / "E   assert ..." lines
    last_e = [line for line in text.splitlines() if line.startswith("E ")]
    return bool(last_e) and last_e[0][1:].strip().startswith(("assert", "AssertionError"))


@dataclass(frozen=True)
class SuiteQuality:
    files: int
    syntax_valid_files: int
    collectable_files: int
    tests: int
    oracle_reached: int
    passed: int
    reruns: int
    flaky: tuple[str, ...]  # tests whose outcome differed between clean re-executions

    @property
    def stable(self) -> int:
        return self.tests - len(self.flaky)

    def summary(self) -> dict[str, Any]:
        return {
            "files": self.files,
            "syntax_valid_rate": ratio(self.syntax_valid_files, self.files),
            "collectable_rate": ratio(self.collectable_files, self.files),
            "tests": self.tests,
            "oracle_reached_rate": ratio(self.oracle_reached, self.tests),
            "pass_rate": ratio(self.passed, self.tests),
            "reruns": self.reruns,
            "stable_rate": ratio(self.stable, self.tests) if self.reruns > 1 else None,
            "flaky_tests": list(self.flaky),
        }


def suite_quality(
    files: Sequence[Path],
    collectable: Mapping[Path, bool],
    runs: Sequence[Iterable[TestResult]],
) -> SuiteQuality:
    """``runs[0]`` is the reference run; later entries are clean re-executions."""
    if not runs:
        raise MeasurementError("at least one test run is needed")
    first = list(runs[0])
    by_test: dict[str, set[Outcome]] = {r.test_id: {r.outcome} for r in first}
    for run in runs[1:]:
        seen = set()
        for result in run:
            by_test.setdefault(result.test_id, set()).add(result.outcome)
            seen.add(result.test_id)
        for test_id in by_test.keys() - seen:  # a test that vanished is unstable too
            by_test[test_id].add(Outcome.ERROR)
    flaky = tuple(sorted(t for t, outcomes in by_test.items() if len(outcomes) > 1))
    return SuiteQuality(
        files=len(files),
        syntax_valid_files=sum(syntax_valid(f) for f in files),
        collectable_files=sum(bool(collectable.get(f)) for f in files),
        tests=len(first),
        oracle_reached=sum(r.outcome.reached_oracle for r in first),
        passed=sum(r.outcome is Outcome.PASSED for r in first),
        reruns=len(runs),
        flaky=flaky,
    )
