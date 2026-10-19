from pathlib import Path

import pytest

from restgen.errors import MeasurementError
from restgen.evaluation.suite import Outcome, TestResult, read_junit, suite_quality, syntax_valid

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="5">
  <testcase classname="test_api" name="test_ok" time="0.1"/>
  <testcase classname="test_api" name="test_assert" time="0.1">
    <failure message="AssertionError: assert 500 &lt; 500">long</failure>
  </testcase>
  <testcase classname="test_api" name="test_pytest_assert" time="0.1">
    <failure message="assert 1 == 2">E   assert 1 == 2</failure>
  </testcase>
  <testcase classname="test_api" name="test_setup_crash" time="0.1">
    <failure message="httpx.ConnectError: refused">E   httpx.ConnectError</failure>
  </testcase>
  <testcase classname="test_api" name="test_fixture" time="0.0">
    <error message="fixture 'db' not found"/>
  </testcase>
  <testcase classname="test_api" name="test_skip" time="0.0"><skipped message="later"/></testcase>
</testsuite></testsuites>
"""


def test_read_junit_classifies_outcomes(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(JUNIT)
    outcomes = {r.test_id.split("::")[1]: r.outcome for r in read_junit(report)}
    assert outcomes == {
        "test_ok": Outcome.PASSED,
        "test_assert": Outcome.ASSERTION_FAILED,
        "test_pytest_assert": Outcome.ASSERTION_FAILED,
        "test_setup_crash": Outcome.FAILED,
        "test_fixture": Outcome.ERROR,
        "test_skip": Outcome.SKIPPED,
    }


def test_bad_junit(tmp_path: Path) -> None:
    with pytest.raises(MeasurementError):
        read_junit(tmp_path / "missing.xml")


def test_suite_quality_stages_and_flakiness(tmp_path: Path) -> None:
    good, bad = tmp_path / "test_a.py", tmp_path / "test_b.py"
    good.write_text("def test_x():\n    assert True\n")
    bad.write_text("def test_y(:\n")
    assert syntax_valid(good) and not syntax_valid(bad)

    first = [
        TestResult("a::1", Outcome.PASSED),
        TestResult("a::2", Outcome.ASSERTION_FAILED),
        TestResult("a::3", Outcome.FAILED),
        TestResult("a::4", Outcome.PASSED),
    ]
    rerun = [
        TestResult("a::1", Outcome.PASSED),
        TestResult("a::2", Outcome.ASSERTION_FAILED),
        TestResult("a::3", Outcome.PASSED),  # flaky
    ]  # a::4 vanished: unstable too
    quality = suite_quality([good, bad], {good: True, bad: False}, [first, rerun])
    summary = quality.summary()
    assert summary["syntax_valid_rate"] == 0.5
    assert summary["collectable_rate"] == 0.5
    assert summary["oracle_reached_rate"] == 0.75
    assert summary["pass_rate"] == 0.5
    assert summary["flaky_tests"] == ["a::3", "a::4"]
    assert summary["stable_rate"] == 0.5

    single = suite_quality([good], {good: True}, [first]).summary()
    assert single["stable_rate"] is None
    with pytest.raises(MeasurementError):
        suite_quality([good], {}, [])
