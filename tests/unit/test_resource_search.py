import random
from pathlib import Path

from restgen.abc.dependencies import DependencyGraph
from restgen.abc.rest import RestTestOperator
from restgen.core.representation.action import HttpAction
from restgen.core.representation.templates import build_templates
from restgen.core.representation.testcase import TestCase
from restgen.core.representation.values import ObjectValue, ResponseRef
from restgen.openapi import OpenApiSpec

ROOT = Path(__file__).parents[2]
SHOP = ROOT / "benchmark/examples/shop_api/openapi.json"


def test_openapi_body_name_infers_order_dependency_on_user() -> None:
    templates = build_templates(OpenApiSpec.load(SHOP))
    graph = DependencyGraph(templates)

    assert "POST /users" in graph.prerequisites("POST /orders")
    evidence = graph.evidence("POST /users", "POST /orders")
    assert any(item.source == "openapi-name" and item.input_name == "user_id" for item in evidence)


def test_lifecycle_sampler_chains_response_id_into_dependent_body() -> None:
    templates = build_templates(OpenApiSpec.load(SHOP))
    graph = DependencyGraph(templates)
    operator = RestTestOperator(templates, graph, 1.0, 1.0, 10)

    case = operator.lifecycle("POST /orders", random.Random(2))

    operations = [action.operation.key for action in case.actions]
    assert operations.index("POST /users") < operations.index("POST /orders")
    order = case.actions[operations.index("POST /orders")]
    assert isinstance(order.body, ObjectValue)
    assert isinstance(order.body.fields["user_id"], ResponseRef)
    case.validate()


def test_runtime_and_fitness_evidence_update_graph() -> None:
    templates = build_templates(OpenApiSpec.load(SHOP))
    graph = DependencyGraph(templates)
    graph.learn_state_accesses({"POST /users": {"users"}, "GET /users/{user_id}": {"users"}})
    graph.learn_fitness(("POST /users", "POST /orders"), frozenset({"line:services/orders.py:10"}))

    runtime = graph.evidence("POST /users", "GET /users/{user_id}")
    feedback = graph.evidence("POST /users", "POST /orders")
    assert any(item.source == "python-state" for item in runtime)
    assert any(item.source == "fitness-feedback" for item in feedback)


def test_resource_mutation_can_reorder_independent_actions() -> None:
    templates = build_templates(OpenApiSpec.load(SHOP))
    by_key = {template.key: template for template in templates}
    case = TestCase(
        [
            HttpAction.placeholder(by_key["GET /users"]),
            HttpAction.placeholder(by_key["GET /health"]),
        ]
    )

    RestTestOperator._reorder_independent(case, random.Random(1))

    assert [action.operation.key for action in case.actions] == ["GET /health", "GET /users"]
