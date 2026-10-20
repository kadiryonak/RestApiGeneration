import json
from pathlib import Path
from typing import Any

import pytest

from restgen.errors import SpecError
from restgen.openapi import OpenApiSpec, parse_document

OAS3: dict[str, Any] = {
    "openapi": "3.0.3",
    "servers": [{"url": "http://localhost:8080/api/v1"}],
    "paths": {
        "/users": {
            "get": {"responses": {"200": {}}},
            "post": {
                "operationId": "createUser",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/User"}}
                    },
                },
                "responses": {"201": {}, "400": {}},
            },
        },
        "/users/{id}": {
            "parameters": [{"name": "id", "in": "path", "schema": {"type": "integer"}}],
            "get": {
                "parameters": [{"name": "verbose", "in": "query", "schema": {"type": "boolean"}}],
                "responses": {"200": {}, "404": {}},
            },
            "delete": {"responses": {"204": {}}},
        },
        "/users/me": {"get": {"responses": {"200": {}}}},
    },
    "components": {
        "schemas": {
            "User": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "example": "Ada"},
                    "manager": {"$ref": "#/components/schemas/User"},
                    "nickname": {"type": "string", "nullable": True},
                },
            }
        }
    },
}

SWAGGER2: dict[str, Any] = {
    "swagger": "2.0",
    "basePath": "/v2",
    "paths": {
        "/pets/{petId}": {
            "put": {
                "parameters": [
                    {"name": "petId", "in": "path", "required": True, "type": "integer"},
                    {"name": "body", "in": "body", "required": True, "schema": {"type": "object"}},
                ],
                "responses": {"200": {}},
            }
        }
    },
}


@pytest.fixture
def spec() -> OpenApiSpec:
    return OpenApiSpec(OAS3)


def test_operations_are_method_and_template(spec: OpenApiSpec) -> None:
    keys = {operation.key for operation in spec.operations}
    assert keys == {
        "GET /users",
        "POST /users",
        "GET /users/{id}",
        "DELETE /users/{id}",
        "GET /users/me",
    }


def test_path_level_parameters_are_merged(spec: OpenApiSpec) -> None:
    operation = spec.operation("GET /users/{id}")
    names = {(p.name, p.location, p.required) for p in operation.parameters}
    assert names == {("id", "path", True), ("verbose", "query", False)}


def test_base_path_comes_from_servers(spec: OpenApiSpec) -> None:
    assert spec.base_path == "/api/v1"


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/api/v1/users", "GET /users"),
        ("get", "/api/v1/users/", "GET /users"),
        ("GET", "/api/v1/users/42?verbose=true", "GET /users/{id}"),
        ("DELETE", "/api/v1/users/42", "DELETE /users/{id}"),
        ("GET", "/api/v1/users/me", "GET /users/me"),
        ("GET", "/api/v1/users/a%20b", "GET /users/{id}"),
    ],
)
def test_match_maps_concrete_requests(
    spec: OpenApiSpec, method: str, path: str, expected: str
) -> None:
    matched = spec.match(method, path)
    assert matched.operation is not None
    assert matched.operation.key == expected


@pytest.mark.parametrize(
    ("method", "path"),
    [("PUT", "/api/v1/users/42"), ("GET", "/openapi.json"), ("GET", "/api/v1/users/1/x")],
)
def test_unmatched_requests_have_no_operation(spec: OpenApiSpec, method: str, path: str) -> None:
    assert spec.match(method, path).operation is None


def test_request_body_schema_is_self_contained(spec: OpenApiSpec) -> None:
    operation = spec.operation("POST /users")
    assert operation.body_required
    body = operation.json_body
    assert body is not None
    assert body["required"] == ["name"]
    assert "$ref" not in json.dumps(body)
    assert "example" not in body["properties"]["name"]
    assert body["properties"]["nickname"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}


def test_recursive_schema_is_cut_off(spec: OpenApiSpec) -> None:
    body = spec.operation("POST /users").json_body
    assert body is not None
    depth = 0
    node: Any = body
    while isinstance(node, dict) and "manager" in node.get("properties", {}):
        node = node["properties"]["manager"]
        depth += 1
    assert 1 <= depth <= 9


def test_swagger2_body_and_base_path() -> None:
    spec = OpenApiSpec(SWAGGER2)
    assert spec.base_path == "/v2"
    operation = spec.operation("PUT /pets/{petId}")
    assert operation.json_body == {"type": "object"}
    assert operation.parameters[0].schema == {"type": "integer"}
    matched = spec.match("PUT", "/v2/pets/7").operation
    assert matched is not None
    assert matched.key == "PUT /pets/{petId}"


def test_load_from_yaml_file(tmp_path: Path) -> None:
    path = tmp_path / "openapi.yaml"
    path.write_text("openapi: 3.0.0\npaths:\n  /ping:\n    get:\n      responses: {}\n")
    spec = OpenApiSpec.load(path)
    assert [operation.key for operation in spec.operations] == ["GET /ping"]
    assert spec.version == "3.0.0"


def test_invalid_documents_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(SpecError):
        OpenApiSpec({"openapi": "3.0.0"})
    with pytest.raises(SpecError):
        parse_document("[1, 2]")
    with pytest.raises(SpecError):
        OpenApiSpec.load(tmp_path / "missing.json")


def test_external_refs_are_rejected() -> None:
    spec = OpenApiSpec({"paths": {}})
    with pytest.raises(SpecError, match="local"):
        spec.json_schema({"$ref": "other.yaml#/User"})


def test_flasgger_hybrid_document_uses_servers() -> None:
    # flasgger emits both "swagger": "3.0" and "openapi": "3.0.0", servers and definitions
    hybrid = {
        "swagger": "3.0",
        "openapi": "3.0.0",
        "servers": [{"url": "/api/v1"}],
        "definitions": {},
        "paths": {"/technologies": {"get": {"responses": {"200": {}}}}},
    }
    spec = OpenApiSpec(hybrid)
    assert spec.base_path == "/api/v1"
    assert spec.version == "3.0.0"
    matched = spec.match("GET", "/api/v1/technologies").operation
    assert matched is not None and matched.key == "GET /technologies"
