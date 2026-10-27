"""From an OpenAPI document to operation templates to a test case, on the Shop API.

1. read benchmark/examples/shop_api/openapi.json and print every operation template
   (fixed part: method + path; variable part: its input positions);
2. build a 3-action test case by hand: create an ADMIN user, read it back by the id the
   first response returned, order two laptops for it (total 1900 > 1000: needs ADMIN);
3. print the test case and, with --url, send it to a running Shop API.

Run (from the repository root):
    .venv/bin/python example/representation/demo_testcase.py
    .venv/bin/python example/representation/demo_testcase.py --url http://127.0.0.1:8000
"""

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

from restgen.core.representation.action import HttpAction
from restgen.core.representation.templates import OperationTemplate, build_templates
from restgen.core.representation.testcase import TestCase
from restgen.core.representation.values import (
    ABSENT,
    EnumValue,
    IntegerValue,
    ObjectValue,
    OptionalValue,
    ResponseRef,
    StringValue,
    placeholder,
)
from restgen.openapi import OpenApiSpec

OPENAPI = Path(__file__).parents[2] / "benchmark/examples/shop_api/openapi.json"


def show_templates(templates: dict[str, OperationTemplate]) -> None:
    print("== Operation templates ==")
    for template in templates.values():
        print(f"\n{template.key}   (operationId: {template.operation_id})")
        for position in template.inputs:
            need = "required" if position.required else "optional"
            print(f"  {position.key:<16} {need:<9} {json.dumps(position.spec.describe())}")


def build_case(templates: dict[str, OperationTemplate]) -> TestCase:
    create_user = templates["POST /users"]
    assert create_user.body is not None
    user = placeholder(create_user.body.spec)  # required fields set, optional ones absent
    assert isinstance(user, ObjectValue)
    for name, text in (("name", "Ada"), ("email", "ada@shop.com"), ("country", "US")):
        field = user.fields[name]
        assert isinstance(field, StringValue)
        field.value = text
    age = user.fields["age"]
    assert isinstance(age, IntegerValue)
    age.value = 30
    role = user.fields["role"]  # optional: make it present and pick "ADMIN"
    assert isinstance(role, OptionalValue) and isinstance(role.inner, EnumValue)
    role.present = True
    role.inner.index = role.inner.spec.values.index("ADMIN")

    get_user = templates["GET /users/{user_id}"]
    user_id = get_user.inputs[0]

    create_order = templates["POST /orders"]
    assert create_order.body is not None
    order = placeholder(create_order.body.spec)
    assert isinstance(order, ObjectValue)
    # user_id is not chosen: it is whatever id the first action's response contains
    user_id_spec = order.fields["user_id"].spec
    order.fields["user_id"] = ResponseRef(user_id_spec, action=0, path="$.id")
    product = order.fields["product"]
    assert isinstance(product, StringValue)
    product.value = "laptop"
    quantity = order.fields["quantity"]
    assert isinstance(quantity, IntegerValue)
    quantity.value = 2

    case = TestCase(
        [
            HttpAction(create_user, body=user),
            HttpAction(get_user, {user_id.key: ResponseRef(user_id.spec, action=0, path="$.id")}),
            HttpAction(create_order, body=order),
        ]
    )
    case.validate()
    return case


def run(case: TestCase, url: str) -> None:
    print(f"\n== Sending to {url} ==")
    responses: list[Any] = []
    with httpx.Client(base_url=url) as client:
        for index in range(len(case)):
            request = case.request(index, responses)
            response = client.request(
                request.method,
                request.path,
                params=list(request.query),
                json=None if request.body is ABSENT else request.body,
            )
            print(f"[{index}] {request.method} {request.path} -> {response.status_code}")
            print(f"    {response.text}")
            responses.append(response.json())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="base URL of a running Shop API")
    args = parser.parse_args()

    templates = {t.key: t for t in build_templates(OpenApiSpec.load(OPENAPI))}
    show_templates(templates)
    case = build_case(templates)
    print("\n== Test case ==")
    print(json.dumps(case.describe(), indent=2))
    if args.url:
        run(case, args.url)


if __name__ == "__main__":
    main()
