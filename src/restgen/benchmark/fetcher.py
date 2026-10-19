"""Check out every suite at its pinned commit and prove that it is the pinned one."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from restgen.benchmark.models import Suite
from restgen.errors import BenchmarkError
from restgen.jsonio import write_json

FETCH_RECORD = "fetch.json"


@dataclass(frozen=True)
class SuiteStatus:
    suite: str
    path: Path
    present: bool
    head: str | None
    pinned: bool  # HEAD equals the manifest commit
    clean: bool  # no tracked file modified

    @property
    def ok(self) -> bool:
        return self.present and self.pinned and self.clean


class SuiteFetcher:
    """Suites live in ``<benchmark_dir>/suites/<name>`` (git-ignored)."""

    def __init__(self, benchmark_dir: Path) -> None:
        self.root = benchmark_dir / "suites"

    def path(self, suite: Suite) -> Path:
        return self.root / suite.name

    def fetch(self, suite: Suite) -> SuiteStatus:
        target = self.path(suite)
        if not (target / ".git").is_dir():
            target.parent.mkdir(parents=True, exist_ok=True)
            # Partial clone: full history is reachable, blobs are downloaded on demand.
            _git(["clone", "--filter=blob:none", "--no-checkout", suite.repository, str(target)])
        if not self.verify(suite).ok:
            # A --no-checkout clone already has HEAD at the default branch but an empty
            # worktree, so check out even when HEAD looks right.
            if not _git_ok(["cat-file", "-e", f"{suite.commit}^{{commit}}"], cwd=target):
                _git(["fetch", "--filter=blob:none", "origin", suite.commit], cwd=target)
            _git(["checkout", "--detach", "--force", suite.commit], cwd=target)
        status = self.verify(suite)
        if not status.ok:
            raise BenchmarkError(f"suite {suite.name} is not at the pinned commit after fetching")
        write_json(
            target.parent / f"{suite.name}.{FETCH_RECORD}",
            {
                "suite": suite.name,
                "repository": suite.repository,
                "commit": suite.commit,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
        )
        return status

    def verify(self, suite: Suite) -> SuiteStatus:
        target = self.path(suite)
        if not (target / ".git").is_dir():
            return SuiteStatus(suite.name, target, False, None, False, False)
        head = _git(["rev-parse", "HEAD"], cwd=target, check=False) or None
        dirty = _git(["status", "--porcelain", "--untracked-files=no"], cwd=target, check=False)
        return SuiteStatus(
            suite=suite.name,
            path=target,
            present=True,
            head=head,
            pinned=head == suite.commit,
            clean=dirty == "",
        )


def _git(args: list[str], cwd: Path | None = None, check: bool = True) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=1800
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BenchmarkError(f"git {' '.join(args)} failed: {exc}") from exc
    if check and result.returncode != 0:
        raise BenchmarkError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_ok(args: list[str], cwd: Path) -> bool:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
