import os
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from restgen.abc.archive import TargetArchive
from restgen.abc.codegen import pytest_suite
from restgen.abc.dependencies import DependencyGraph
from restgen.abc.engine import DabcHs, DabcHsConfig
from restgen.abc.fitness import RestFitnessEvaluator
from restgen.abc.rest import RestTestOperator
from restgen.benchmark.service import free_port
from restgen.core.representation.inputs import IntegerInput
from restgen.core.representation.templates import InputPosition, Location, OperationTemplate
from restgen.core.representation.testcase import TestCase

pytestmark = pytest.mark.integration

SERVICE = """\
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(201)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'id': 1}).encode())

    def do_GET(self):
        has_body = int(self.headers.get('Content-Length', '0')) > 0
        status = 200 if self.path == '/items/1' and not has_body else 404
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'id': 1} if status == 200 else {'detail': 'missing'}).encode())

    def log_message(self, format, *args):
        pass

HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
"""


class LifecycleOnly:
    def __init__(self, wrapped: RestTestOperator) -> None:
        self.wrapped = wrapped

    def sample(self, archive: TargetArchive[TestCase], rng: random.Random) -> TestCase:
        return self.wrapped.lifecycle("GET /items/{item_id}", rng)

    def mutate(
        self,
        candidate: TestCase,
        mutations: int,
        archive: TargetArchive[TestCase],
        rng: random.Random,
    ) -> TestCase:
        return candidate.copy()


def test_search_executes_resource_chain_against_real_http_service(tmp_path: Path) -> None:
    service = tmp_path / "service.py"
    service.write_text(SERVICE, encoding="utf-8")
    port = free_port()
    process = subprocess.Popen([sys.executable, str(service), str(port)])
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(50):
            try:
                httpx.get(url + "/ready", timeout=0.1)
                break
            except httpx.HTTPError:
                time.sleep(0.02)
        post = OperationTemplate("POST", "/items", "", None, None, (), ("201",))
        item_id = InputPosition(Location.PATH, "item_id", IntegerInput(minimum=1), True)
        get = OperationTemplate(
            "GET", "/items/{item_id}", "", None, None, (item_id,), ("200", "404")
        )
        templates = (post, get)
        rest = RestTestOperator(templates, DependencyGraph(templates), 1.0, 1.0, 4)
        result = DabcHs(
            DabcHsConfig(2, 2, 2, 4, 1, 2, (0.5, 1.0), 1, 2, 6),
            LifecycleOnly(rest),
            RestFitnessEvaluator(url, {}, 1.0),
            len,
            seed=4,
        ).run()

        assert "status:POST /items:201" in result.archive.covered
        assert "status:GET /items/{item_id}:200" in result.archive.covered
        saved = result.archive.population("status:GET /items/{item_id}:200")[0].candidate
        assert [action.operation.key for action in saved.actions] == [
            "POST /items",
            "GET /items/{item_id}",
        ]
        suite = tmp_path / "test_generated.py"
        suite.write_text(pytest_suite([saved]), encoding="utf-8")
        environment = {
            **os.environ,
            "RESTGEN_BASE_URL": url,
            "RESTGEN_HEADERS": "{}",
            "RESTGEN_REQUEST_TIMEOUT": "1",
        }
        rerun = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(suite)],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    finally:
        process.terminate()
        process.wait(timeout=5)
