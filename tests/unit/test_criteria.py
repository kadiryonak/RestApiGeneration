import json
from typing import Any

from restgen.evaluation.criteria import coverage_criteria
from restgen.openapi import OpenApiSpec
from restgen.traffic.models import HttpInteraction

SPEC: dict[str, Any] = {
    "openapi": "3.0.0",
    "paths": {
        "/items": {
            "get": {
                "parameters": [
                    {
                        "name": "sort",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["asc", "desc"]},
                    },
                    {"name": "full", "in": "query", "schema": {"type": "boolean"}},
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Item"},
                                }
                            }
                        }
                    }
                },
            },
            "post": {
                "requestBody": {
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Item"}},
                        "application/xml": {"schema": {"type": "object"}},
                    }
                },
                "responses": {
                    "201": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Item"}}
                        }
                    },
                    "400": {},
                },
            },
        },
        "/items/{id}": {
            "parameters": [
                {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}
            ],
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Item"}}
                        }
                    },
                    "404": {},
                }
            },
            "delete": {"responses": {"204": {}}},
        },
        "/health": {"get": {"responses": {"200": {}}}},
    },
    "components": {
        "schemas": {
            "Item": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "object", "properties": {"label": {"type": "string"}}},
                    },
                },
            }
        }
    },
}


def _call(
    t: float,
    method: str,
    target: str,
    status: int | None,
    *,
    body: Any = None,
    response: Any = None,
    request_type: str | None = None,
    response_type: str = "application/json",
) -> HttpInteraction:
    request_body = json.dumps(body) if body is not None else ""
    response_body = json.dumps(response) if response is not None else ""
    return HttpInteraction(
        sequence=int(t),
        started_at=t,
        duration_ms=1.0,
        method=method,
        target=target,
        request_headers={"content-type": request_type} if request_type else {},
        request_body=request_body,
        request_body_size=len(request_body),
        status=status,
        response_headers={"content-type": response_type} if response is not None else {},
        response_body=response_body,
        response_body_size=len(response_body),
    )


TRAFFIC = [
    _call(1, "GET", "/items?sort=asc&full=true", 200, response=[{"id": 1, "name": "a"}]),
    _call(
        2,
        "POST",
        "/items",
        400,
        body={"x": 1},
        request_type="application/json",
        response={"error": "bad"},
    ),
    _call(
        3,
        "POST",
        "/items",
        201,
        body={"name": "b"},
        request_type="application/json",
        response={"id": 2, "name": "b", "tags": [{"label": "x"}]},
    ),
    _call(4, "GET", "/items/2", 200, response={"id": 2}),
    _call(5, "DELETE", "/items/2", 204),
    _call(6, "GET", "/openapi.json", 200, response={}),  # not an operation
]


def test_all_ten_criteria() -> None:
    result = coverage_criteria(OpenApiSpec(SPEC), TRAFFIC, max_body_bytes=10_000)
    assert result["path"] == {"covered": 2, "total": 3, "ratio": 2 / 3, "missing": ["/health"]}
    assert result["operation"]["covered"] == 4 and result["operation"]["total"] == 5
    # sort, full, POST body, GET/DELETE path id; never: nothing on /health (has none)
    assert (result["parameter"]["covered"], result["parameter"]["total"]) == (5, 5)
    # enum asc/desc + boolean true/false: asc and true sent
    assert (result["parameter_value"]["covered"], result["parameter_value"]["total"]) == (2, 4)
    assert result["parameter_value"]["missing"] == [
        "GET /items query:full=false",
        "GET /items query:sort=desc",
    ]
    assert (result["input_content_type"]["covered"], result["input_content_type"]["total"]) == (
        1,
        2,
    )
    # classes: 5 operations x 2; correct: GET /items, POST, GET id, DELETE; erroneous: POST
    assert (result["status_code_class"]["covered"], result["status_code_class"]["total"]) == (5, 10)
    # documented: GET 200, POST 201+400, GET id 200+404, DELETE 204, health 200 = 7
    assert (result["status_code"]["covered"], result["status_code"]["total"]) == (5, 7)
    assert result["output_content_type"]["covered"] == 3


def test_response_body_properties_and_truncation() -> None:
    full = coverage_criteria(OpenApiSpec(SPEC), TRAFFIC, max_body_bytes=10_000)
    props = full["response_body_properties"]
    # GET /items 200: [].id [].name [].tags [].tags[].label ; POST 201 and GET id 200: 4 each
    assert props["total"] == 12
    assert props["covered"] == 2 + 4 + 1
    truncated = coverage_criteria(OpenApiSpec(SPEC), TRAFFIC, max_body_bytes=10)
    assert truncated["truncated_response_bodies"] > 0
    assert truncated["response_body_properties"]["covered"] < props["covered"]


def test_operation_flows_and_test_coverage_level() -> None:
    result = coverage_criteria(OpenApiSpec(SPEC), TRAFFIC, max_body_bytes=10_000)
    flows = result["operation_flow"]
    # creatable /items: read one, read all, delete (no update operation exists)
    assert flows["total"] == 3
    # read one and delete happened after the successful create; read all only before it
    assert flows["covered"] == 2
    assert result["test_coverage_level"] == 0  # /health was never called
    complete = [*TRAFFIC, _call(7, "GET", "/health", 200)]
    assert coverage_criteria(OpenApiSpec(SPEC), complete, 10_000)["test_coverage_level"] == 2
