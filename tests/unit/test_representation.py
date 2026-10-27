from typing import Any

from restgen.core.representation.inputs import (
    AnyInput,
    ArrayInput,
    BooleanInput,
    ChoiceInput,
    EnumInput,
    IntegerInput,
    ObjectInput,
    RecursiveInput,
    StringInput,
)
from restgen.core.representation.resources import resource_dependencies, summarize
from restgen.core.representation.templates import Location, build_templates
from restgen.openapi import OpenApiSpec

SWAGGER2: dict[str, Any] = {
    "swagger": "2.0",
    "basePath": "/api",
    "consumes": ["application/json"],
    "paths": {
        "/products": {"get": {"responses": {"200": {}}}},
        "/products/{productName}": {
            "parameters": [
                {"name": "productName", "in": "path", "required": True, "type": "string"}
            ],
            "post": {"responses": {"201": {}}},
            "get": {
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                    },
                    {
                        "name": "tags",
                        "in": "query",
                        "type": "array",
                        "collectionFormat": "csv",
                        "items": {"type": "string", "enum": ["a", "b"]},
                    },
                    {"name": "X-Trace", "in": "header", "type": "string", "format": "uuid"},
                ],
                "responses": {"200": {}},
            },
        },
        "/products/{productName}/features/{featureName}": {
            "put": {
                "parameters": [
                    {"name": "productName", "in": "path", "required": True, "type": "string"},
                    {"name": "featureName", "in": "path", "required": True, "type": "string"},
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {"$ref": "#/definitions/Feature"},
                    },
                ],
                "responses": {"200": {}},
            }
        },
        "/products/{name}/constraints/{constraintId}": {
            "delete": {
                "parameters": [
                    {"name": "name", "in": "path", "required": True, "type": "string"},
                    {"name": "constraintId", "in": "path", "required": True, "type": "integer"},
                ],
                "responses": {"204": {}},
            }
        },
        "/upload": {
            "post": {
                "consumes": ["multipart/form-data"],
                "parameters": [
                    {"name": "file", "in": "formData", "type": "file", "required": True}
                ],
                "responses": {"200": {}},
            }
        },
    },
    "definitions": {
        "Feature": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 20},
                "active": {"type": "boolean"},
                "parent": {"$ref": "#/definitions/Feature"},
                "meta": {"type": "object", "additionalProperties": {"type": "integer"}},
                "created": {"type": "string", "format": "date-time"},
            },
        }
    },
}

OAS3: dict[str, Any] = {
    "openapi": "3.1.0",
    "paths": {
        "/pets": {
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "allOf": [
                                    {"$ref": "#/components/schemas/Base"},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "kind": {
                                                "oneOf": [{"type": "string"}, {"type": "integer"}]
                                            }
                                        },
                                    },
                                ]
                            }
                        }
                    },
                },
                "responses": {"201": {}},
            }
        }
    },
    "components": {
        "schemas": {
            "Base": {
                "type": "object",
                "properties": {"nick": {"type": ["string", "null"]}, "ids": {"items": {}}},
            }
        }
    },
}


def _templates(document: dict[str, Any]) -> dict[str, Any]:
    return {t.key: t for t in build_templates(OpenApiSpec(document))}


def test_fixed_parts_and_input_positions() -> None:
    templates = _templates(SWAGGER2)
    get = templates["GET /products/{productName}"]
    assert get.base_path == "/api"
    assert get.media_type is None
    keys = [(i.key, i.required) for i in get.inputs]
    assert keys == [
        ("path:productName", True),
        ("query:limit", False),
        ("query:tags", False),
        ("header:X-Trace", False),
    ]
    limit = get.at(Location.QUERY)[0].spec
    assert limit == IntegerInput(minimum=1, maximum=50)
    tags = get.at(Location.QUERY)[1]
    assert tags.style == "csv"
    assert tags.spec == ArrayInput(item=EnumInput(values=("a", "b")))
    assert get.at(Location.HEADER)[0].spec == StringInput(format="uuid")


def test_body_object_with_recursion_map_and_formats() -> None:
    put = _templates(SWAGGER2)["PUT /products/{productName}/features/{featureName}"]
    assert put.media_type == "application/json"
    body = put.body
    assert body is not None and body.required
    feature = body.spec
    assert isinstance(feature, ObjectInput)
    assert feature.schema_name == "Feature"
    props = {p.name: p for p in feature.properties}
    assert props["name"].required and not props["active"].required
    assert props["name"].spec == StringInput(min_length=1, max_length=20)
    assert props["parent"].spec == RecursiveInput(schema_name="Feature")
    assert props["meta"].spec == ObjectInput(additional=IntegerInput())
    assert props["created"].spec == StringInput(format="date-time")
    # leaves: name, active, parent (cut), meta's values, created
    assert put.scalar_count() == 2 + 5


def test_form_data_becomes_one_body() -> None:
    upload = _templates(SWAGGER2)["POST /upload"]
    assert upload.media_type == "multipart/form-data"
    body = upload.body
    assert body is not None and body.required
    assert isinstance(body.spec, ObjectInput)
    assert body.spec.properties[0].spec == StringInput(format="binary")


def test_openapi31_all_of_one_of_and_nullable_types() -> None:
    post = _templates(OAS3)["POST /pets"]
    body = post.body
    assert body is not None and isinstance(body.spec, ObjectInput)
    props = {p.name: p.spec for p in body.spec.properties}
    assert body.spec.schema_name == "Base"
    assert props["nick"] == StringInput(nullable=True)
    assert props["ids"] == ArrayInput(item=AnyInput())
    assert props["kind"] == ChoiceInput(options=(StringInput(), IntegerInput()))
    assert BooleanInput().kind == "boolean"
    assert props["kind"].describe()["exclusive"] is True


def test_resource_dependencies() -> None:
    templates = list(_templates(SWAGGER2).values())
    found = {(d.operation, d.parameter): d.creators for d in resource_dependencies(templates)}
    # creating a product by name is itself not a dependency
    assert ("POST /products/{productName}", "productName") not in found
    assert found[("GET /products/{productName}", "productName")] == (
        "POST /products/{productName}",
    )
    # /products/{name}/... matches /products/{productName} up to parameter names
    assert found[("DELETE /products/{name}/constraints/{constraintId}", "name")] == (
        "POST /products/{productName}",
    )
    # created by an action endpoint we cannot see: unresolvable
    assert found[("DELETE /products/{name}/constraints/{constraintId}", "constraintId")] == ()
    feature = found[("PUT /products/{productName}/features/{featureName}", "productName")]
    assert feature == ("POST /products/{productName}",)


def test_summary() -> None:
    summary = summarize(build_templates(OpenApiSpec(SWAGGER2)))
    assert summary["operations"] == 6
    assert summary["methods"] == {"DELETE": 1, "GET": 2, "POST": 2, "PUT": 1}
    assert summary["input_positions"]["path"] == 6  # shared path parameter counts per operation
    assert summary["formats"] == {"binary": 1, "date-time": 1, "uuid": 1}
    assert summary["unresolvable_dependencies"] == [
        "DELETE /products/{name}/constraints/{constraintId} (constraintId)"
    ]
    assert "multipart/form-data" in summary["body_media_types"]
