import json
from pathlib import Path

import pytest

from restgen.coverage.models import CodeCoverage, ratio
from restgen.coverage.readers import CoveragePyReader, JacocoXmlReader
from restgen.errors import MeasurementError

COVERAGEPY = {
    "meta": {"version": "7.6.0", "branch_coverage": True},
    "files": {
        "/srv/app/main.py": {
            "executed_lines": [1, 2, 4],
            "missing_lines": [5],
            "executed_branches": [[2, 4]],
            "missing_branches": [[2, 5]],
            "functions": {
                "": {"executed_lines": [1], "missing_lines": []},
                "create": {"executed_lines": [2, 4], "missing_lines": [5]},
                "delete": {"executed_lines": [], "missing_lines": [7]},
            },
        }
    },
}

JACOCO = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">
<report name="svc">
  <package name="org/svc">
    <class name="org/svc/UserController" sourcefilename="UserController.java">
      <method name="get" desc="(J)Lorg/svc/User;" line="10">
        <counter type="LINE" missed="0" covered="2"/>
        <counter type="METHOD" missed="0" covered="1"/>
      </method>
      <method name="delete" desc="(J)V" line="20">
        <counter type="METHOD" missed="1" covered="0"/>
      </method>
    </class>
    <sourcefile name="UserController.java">
      <line nr="10" mi="0" ci="3" mb="1" cb="1"/>
      <line nr="11" mi="0" ci="2" mb="0" cb="0"/>
      <line nr="20" mi="4" ci="0" mb="2" cb="0"/>
    </sourcefile>
  </package>
  <package name="com/thirdparty">
    <sourcefile name="Lib.java"><line nr="1" mi="0" ci="1" mb="0" cb="0"/></sourcefile>
  </package>
</report>
"""


def test_coveragepy_reader(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps(COVERAGEPY))
    coverage = CoveragePyReader(source_root=Path("/srv")).read(report)
    assert coverage.covered_lines == {"app/main.py:1", "app/main.py:2", "app/main.py:4"}
    assert coverage.total_lines == 4
    assert coverage.covered_branches == {"app/main.py:2->4"}
    assert coverage.total_branches == 2
    assert coverage.covered_methods == {"app/main.py:create"}
    assert coverage.total_methods == 2
    assert coverage.line_ratio == 0.75
    assert coverage.branch_ratio == 0.5
    assert coverage.method_ratio == 0.5


def test_coveragepy_without_functions_has_no_method_coverage(tmp_path: Path) -> None:
    data = json.loads(json.dumps(COVERAGEPY))
    del data["files"]["/srv/app/main.py"]["functions"]
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps(data))
    coverage = CoveragePyReader().read(report)
    assert coverage.method_ratio is None
    assert coverage.summary()["methods_total"] is None


def test_jacoco_reader_filters_third_party(tmp_path: Path) -> None:
    report = tmp_path / "jacoco.xml"
    report.write_text(JACOCO)
    coverage = JacocoXmlReader(include_packages=["org/svc"]).read(report)
    assert coverage.covered_lines == {
        "org/svc/UserController.java:10",
        "org/svc/UserController.java:11",
    }
    assert coverage.total_lines == 3
    assert coverage.covered_branches == {"org/svc/UserController.java:10#0"}
    assert coverage.total_branches == 4
    assert coverage.covered_methods == {"org/svc/UserController:get(J)Lorg/svc/User;"}
    assert coverage.total_methods == 2

    everything = JacocoXmlReader().read(report)
    assert everything.total_lines == 4


@pytest.mark.parametrize("content", ["not json", "[]", '{"meta": {}}'])
def test_bad_coveragepy_reports(tmp_path: Path, content: str) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(content)
    with pytest.raises(MeasurementError):
        CoveragePyReader().read(report)


@pytest.mark.parametrize("content", ["<broken", "<other/>"])
def test_bad_jacoco_reports(tmp_path: Path, content: str) -> None:
    report = tmp_path / "jacoco.xml"
    report.write_text(content)
    with pytest.raises(MeasurementError):
        JacocoXmlReader().read(report)


def test_ratio_is_undefined_for_empty_denominator() -> None:
    assert ratio(0, 0) is None
    assert ratio(1, 4) == 0.25


def test_model_round_trip_and_invariants() -> None:
    coverage = CodeCoverage("coveragepy", frozenset({"a:1"}), 2, frozenset(), 0)
    assert CodeCoverage.from_record(coverage.to_record()) == coverage
    assert coverage.branch_ratio is None
    with pytest.raises(MeasurementError):
        CodeCoverage("x", frozenset({"a:1", "a:2"}), 1, frozenset(), 0)
    with pytest.raises(MeasurementError):
        CodeCoverage("x", frozenset(), 0, frozenset(), 0, covered_methods=frozenset())
    with pytest.raises(MeasurementError):
        CodeCoverage.from_record({"tool": "x"})
