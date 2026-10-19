import subprocess
from pathlib import Path

import pytest

from restgen.benchmark.fetcher import SuiteFetcher
from restgen.benchmark.models import Suite, SuiteKind

pytestmark = pytest.mark.integration


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_fetch_checks_out_the_pinned_commit_and_detects_changes(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q", "-b", "main")
    _git(upstream, "config", "user.email", "t@example.org")
    _git(upstream, "config", "user.name", "t")
    (upstream / "app.py").write_text("v = 1\n")
    _git(upstream, "add", "app.py")
    _git(upstream, "commit", "-q", "-m", "one")
    pinned = _git(upstream, "rev-parse", "HEAD")
    (upstream / "app.py").write_text("v = 2\n")
    _git(upstream, "commit", "-q", "-am", "two")  # upstream moved on after the pin

    suite = Suite("demo", SuiteKind.SERVICES, upstream.as_uri(), pinned, "MIT", "key")
    fetcher = SuiteFetcher(tmp_path / "bench")
    assert not fetcher.verify(suite).present

    status = fetcher.fetch(suite)
    assert status.ok
    assert (status.path / "app.py").read_text() == "v = 1\n"
    assert fetcher.fetch(suite).ok  # idempotent

    (status.path / "app.py").write_text("tampered\n")
    modified = fetcher.verify(suite)
    assert modified.pinned and not modified.clean and not modified.ok
