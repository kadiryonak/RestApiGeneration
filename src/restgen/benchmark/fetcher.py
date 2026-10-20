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
        checkout(suite.repository, suite.commit, target)
        status = self.verify(suite)
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
        return checkout_status(suite.name, suite.commit, self.path(suite))


def checkout(repository: str, commit: str, target: Path) -> None:
    """Make ``target`` a clean checkout of ``repository`` at ``commit``."""
    if not (target / ".git").is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
        # Partial clone: full history is reachable, blobs are downloaded on demand.
        _git(["clone", "--filter=blob:none", "--no-checkout", repository, str(target)])
    if not checkout_status("", commit, target).ok:
        # A --no-checkout clone already has HEAD at the default branch but an empty
        # worktree, so check out even when HEAD looks right.
        if not _git_ok(["cat-file", "-e", f"{commit}^{{commit}}"], cwd=target):
            _git(["fetch", "--filter=blob:none", "origin", commit], cwd=target)
        _git(["checkout", "--detach", "--force", commit], cwd=target)
    if not checkout_status("", commit, target).ok:
        raise BenchmarkError(f"{target} is not at the pinned commit {commit} after fetching")


def checkout_status(name: str, commit: str, target: Path) -> SuiteStatus:
    if not (target / ".git").is_dir():
        return SuiteStatus(name, target, False, None, False, False)
    head = _git(["rev-parse", "HEAD"], cwd=target, check=False) or None
    dirty = _git(["status", "--porcelain", "--untracked-files=no"], cwd=target, check=False)
    return SuiteStatus(
        suite=name, path=target, present=True, head=head, pinned=head == commit, clean=dirty == ""
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
