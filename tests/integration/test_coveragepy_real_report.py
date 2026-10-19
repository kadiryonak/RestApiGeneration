import subprocess
import sys
from pathlib import Path

import pytest

from restgen.coverage.readers import CoveragePyReader

pytestmark = pytest.mark.integration

MODULE = """\
def classify(n):
    if n > 0:
        return "positive"
    return "other"


def unused():
    return 1


classify(5)
"""


def test_reads_a_report_produced_by_coverage_py(tmp_path: Path) -> None:
    (tmp_path / "target.py").write_text(MODULE)
    data = tmp_path / ".coverage"
    run = [sys.executable, "-m", "coverage"]
    subprocess.run(
        [*run, "run", "--branch", f"--data-file={data}", "target.py"], cwd=tmp_path, check=True
    )
    subprocess.run(
        [*run, "json", f"--data-file={data}", "-o", "coverage.json"], cwd=tmp_path, check=True
    )

    coverage = CoveragePyReader(source_root=tmp_path).read(tmp_path / "coverage.json")

    assert "target.py:3" in coverage.covered_lines  # return "positive"
    assert "target.py:4" not in coverage.covered_lines  # return "other"
    assert "target.py:8" not in coverage.covered_lines  # body of unused()
    assert coverage.branch_ratio == 0.5
    assert coverage.covered_methods == {"target.py:classify"}
    assert coverage.total_methods == 2
