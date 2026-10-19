import ast
from pathlib import Path

import pytest

from restgen.baselines.base import ToolRunContext
from restgen.baselines.hypothesis_pytest import HypothesisPytest, render_suite, suite_test_name
from restgen.baselines.schemathesis_cli import SchemathesisCli
from restgen.config import BudgetSettings, HypothesisSettings, SchemathesisSettings
from restgen.errors import ToolError
from restgen.openapi import OpenApiSpec

SPEC = OpenApiSpec(
    {
        "openapi": "3.0.0",
        "servers": [{"url": "/api"}],
        "paths": {
            "/users/{id}": {
                "get": {
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        },
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {}},
                }
            },
            "/users-{id}": {"get": {"responses": {"200": {}}}},
            "/users": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"n": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"201": {}},
                }
            },
        },
    }
)
BUDGET = BudgetSettings(max_time_seconds=30, max_examples=7, request_timeout_seconds=5.0)


def _context(tmp_path: Path) -> ToolRunContext:
    return ToolRunContext(
        base_url="http://127.0.0.1:1234",
        openapi_url="http://127.0.0.1:1234/openapi.json",
        headers={"Authorization": "Bearer t"},
        seed=42,
        budget=BUDGET,
        output_dir=tmp_path / "tool",
    )


def test_schemathesis_command_follows_benchmarking_guide(tmp_path: Path) -> None:
    executable = tmp_path / "schemathesis"
    executable.write_text("")
    tool = SchemathesisCli(SchemathesisSettings(executable, ("--no-shrink",)))
    argv = tool.command(_context(tmp_path))
    assert argv[:3] == [str(executable), "run", "http://127.0.0.1:1234/openapi.json"]
    joined = " ".join(argv)
    assert "--max-time 30" in joined
    assert "--seed 42" in joined
    assert "--url http://127.0.0.1:1234" in joined
    assert "--header Authorization: Bearer t" in joined
    assert argv[-1] == "--no-shrink"
    assert not tool.produces_suite
    with pytest.raises(ToolError):
        tool.collect([])


def test_schemathesis_missing_executable(tmp_path: Path) -> None:
    tool = SchemathesisCli(SchemathesisSettings(tmp_path / "missing", ()))
    with pytest.raises(ToolError, match="not found"):
        tool.command(_context(tmp_path))


def test_rendered_suite_is_valid_python_with_one_test_per_operation() -> None:
    source = render_suite(SPEC, seed=42, max_examples=7)
    tree = ast.parse(source)
    tests = [
        n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]
    assert len(tests) == 3
    assert len(set(tests)) == 3  # /users/{id} and /users-{id} collide after sanitising
    assert "max_examples=7" in source
    assert "SEED = 42" in source
    assert "BASE_PATH = '/api'" in source


def test_test_names_are_unique() -> None:
    taken: set[str] = set()
    first = SPEC.operation("GET /users/{id}")
    second = SPEC.operation("GET /users-{id}")
    assert suite_test_name(first, taken) == "test_get_users_id"
    assert suite_test_name(second, taken) == "test_get_users_id_2"


def test_hypothesis_tool_generates_suite(tmp_path: Path) -> None:
    tool = HypothesisPytest(HypothesisSettings(tmp_path / "python"), SPEC)
    assert tool.produces_suite
    suite = tool.generate(_context(tmp_path))
    assert suite.is_file()
    with pytest.raises(ToolError, match="make tools"):
        tool.version()
