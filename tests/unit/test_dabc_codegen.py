import random
from pathlib import Path

from restgen.abc.codegen import pytest_suite
from restgen.abc.dependencies import DependencyGraph
from restgen.abc.rest import RestTestOperator
from restgen.core.representation.action import HttpAction
from restgen.core.representation.templates import build_templates
from restgen.core.representation.testcase import TestCase
from restgen.openapi import OpenApiSpec

ROOT = Path(__file__).parents[2]
SHOP = ROOT / "benchmark/examples/shop_api/openapi.json"


def test_generated_suite_is_valid_python_and_keeps_response_references() -> None:
    templates = build_templates(OpenApiSpec.load(SHOP))
    operator = RestTestOperator(templates, DependencyGraph(templates), 1.0, 1.0, 10)
    case = operator.lifecycle("POST /orders", random.Random(2))

    generated = pytest_suite([case])

    compile(generated, "test_generated.py", "exec")
    assert "'from_action': 0" in generated
    assert "POST" in generated and "/orders" in generated


def test_generated_request_distinguishes_no_body_from_json_null() -> None:
    templates = {template.key: template for template in build_templates(OpenApiSpec.load(SHOP))}
    generated = pytest_suite([TestCase([HttpAction.placeholder(templates["GET /health"])])])

    assert "_call('GET'" in generated
    assert "False, None, responses" in generated
