"""A service that writes its state into tracked files starts clean every time."""

import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from restgen.benchmark.fetcher import checkout
from restgen.benchmark.models import (
    Category,
    CoverageKind,
    CoverageSpec,
    Launch,
    LaunchKind,
    Role,
    Service,
)
from restgen.benchmark.service import ServiceEnvironment, ServiceProcess

pytestmark = pytest.mark.integration

SERVER = """\
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

def count():
    with open("state.txt") as handle:
        return handle.read().count("x")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = str(count()).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        with open("state.txt", "a") as handle:
            handle.write("x")
        self.send_response(201); self.send_header("Content-Length", "0"); self.end_headers()
    def log_message(self, *args):
        pass

HTTPServer(("127.0.0.1", int(os.environ["PORT"])), Handler).serve_forever()
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_reset_paths_restore_tracked_state(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q", "-b", "main")
    _git(upstream, "config", "user.email", "t@example.org")
    _git(upstream, "config", "user.name", "t")
    (upstream / "server.py").write_text(SERVER)
    (upstream / "state.txt").write_text("")
    (upstream / "settings.py").write_text("NAME = 'a'\n")
    _git(upstream, "add", ".")
    _git(upstream, "commit", "-q", "-m", "one")
    commit = _git(upstream, "rev-parse", "HEAD")

    service = Service(
        name="stateful",
        suite="local",
        language="python",
        framework="http.server",
        category=Category.ARTIFICIAL,
        role=Role.DEVELOPMENT,
        openapi="/",
        health="/",
        launch=Launch(
            kind=LaunchKind.COMMAND,
            argv=(sys.executable, "server.py"),
            env={"PORT": "{port}"},
            source_repository=upstream.as_uri(),
            source_commit=commit,
            reset_paths=("state.txt",),
        ),
        coverage=CoverageSpec(kind=CoverageKind.NONE),
    )
    environment = ServiceEnvironment(service, tmp_path / "bench", tmp_path)
    # only the source checkout of setup is needed here (no packages to install)
    checkout(service.launch.source_repository, commit, environment.source)
    environment.venv.mkdir(parents=True)
    (environment.venv / "bin").mkdir()
    (environment.venv / "bin" / "python").write_text("")  # marks the environment ready

    for _ in range(2):
        with ServiceProcess(service, environment, tmp_path, tmp_path / "log") as process:
            assert httpx.get(process.base_url).text == "0"  # clean state on every start
            httpx.post(process.base_url)
            httpx.post(process.base_url)
            assert httpx.get(process.base_url).text == "2"
