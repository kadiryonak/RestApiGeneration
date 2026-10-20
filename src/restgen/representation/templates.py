"""Operation templates: the fixed part of every request and its variable input positions.

Fixed (decided by the document, never searched): HTTP method, path template, base path,
request media type. Variable: one :class:`InputPosition` per path / query / header /
cookie parameter and the request body, each with its :mod:`input specification
<restgen.representation.inputs>`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from restgen.errors import SpecError
from restgen.openapi import HTTP_METHODS, OpenApiSpec
from restgen.representation.inputs import (
    AnyInput,
    ArrayInput,
    BooleanInput,
    ChoiceInput,
    EnumInput,
    InputSpec,
    IntegerInput,
    NumberInput,
    ObjectInput,
    Property,
    RecursiveInput,
    StringInput,
)

JSON_MEDIA = "application/json"
FORM_MEDIA = ("application/x-www-form-urlencoded", "multipart/form-data")


class Location(StrEnum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"
    BODY = "body"


@dataclass(frozen=True)
class InputPosition:
    location: Location
    name: str  # parameter name; "body" for the request body
    spec: InputSpec
    required: bool
    style: str | None = None  # serialisation of arrays/objects (form, csv, multi, ...)

    @property
    def key(self) -> str:
        return f"{self.location.value}:{self.name}"


@dataclass(frozen=True)
class OperationTemplate:
    method: str
    path: str
    base_path: str
    operation_id: str | None
    media_type: str | None  # of the request body; None when there is no body
    inputs: tuple[InputPosition, ...]
    responses: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    def at(self, location: Location) -> tuple[InputPosition, ...]:
        return tuple(i for i in self.inputs if i.location is location)

    @property
    def body(self) -> InputPosition | None:
        return next((i for i in self.inputs if i.location is Location.BODY), None)

    def scalar_count(self) -> int:
        """Number of scalar positions (leaves) over all inputs."""
        return sum(1 for i in self.inputs for _ in i.spec.leaves())


def build_templates(spec: OpenApiSpec) -> tuple[OperationTemplate, ...]:
    builder = _Builder(spec)
    templates = []
    for path, raw_item in spec.document["paths"].items():
        item = spec.resolve(raw_item)
        if not isinstance(item, Mapping):
            continue
        for method in HTTP_METHODS:
            operation = item.get(method)
            if isinstance(operation, Mapping):
                templates.append(builder.operation(method, str(path), item, operation))
    return tuple(templates)


class _Builder:
    def __init__(self, spec: OpenApiSpec) -> None:
        self.spec = spec
        self.swagger2 = "swagger" in spec.document

    def operation(
        self, method: str, path: str, item: Mapping[str, Any], operation: Mapping[str, Any]
    ) -> OperationTemplate:
        inputs: dict[tuple[str, str], InputPosition] = {}
        media: str | None = None
        form_fields: list[Property] = []
        for raw in [*(item.get("parameters") or []), *(operation.get("parameters") or [])]:
            param = self.spec.resolve(raw)
            if not isinstance(param, Mapping) or "in" not in param or "name" not in param:
                continue
            where, name = str(param["in"]), str(param["name"])
            if where == "body":  # Swagger 2.0
                media = self._swagger2_media(operation)
                inputs[("body", "body")] = InputPosition(
                    Location.BODY,
                    "body",
                    self.schema(param.get("schema") or {}, ()),
                    bool(param.get("required", False)),
                )
            elif where == "formData":  # Swagger 2.0 form fields become one object body
                form_fields.append(
                    Property(name, self._param_schema(param), bool(param.get("required", False)))
                )
            elif where in ("path", "query", "header", "cookie"):
                inputs[(where, name)] = InputPosition(
                    Location(where),
                    name,
                    self._param_schema(param),
                    bool(param.get("required", where == "path")),
                    style=param.get("style") or param.get("collectionFormat"),
                )
        if form_fields:
            consumes = operation.get("consumes") or self.spec.document.get("consumes") or []
            media = next((m for m in consumes if m in FORM_MEDIA), FORM_MEDIA[0])
            inputs[("body", "body")] = InputPosition(
                Location.BODY,
                "body",
                ObjectInput(properties=tuple(form_fields)),
                any(f.required for f in form_fields),
            )
        body = self.spec.resolve(operation.get("requestBody"))
        if isinstance(body, Mapping):  # OpenAPI 3
            content = body.get("content") or {}
            media = _pick_media(list(content))
            if media is not None:
                inputs[("body", "body")] = InputPosition(
                    Location.BODY,
                    "body",
                    self.schema(content[media].get("schema") or {}, ()),
                    bool(body.get("required", False)),
                )
        return OperationTemplate(
            method=method.upper(),
            path=path,
            base_path=self.spec.base_path,
            operation_id=operation.get("operationId"),
            media_type=media if ("body", "body") in inputs else None,
            inputs=tuple(inputs.values()),
            responses=tuple(str(code) for code in (operation.get("responses") or {})),
        )

    def _swagger2_media(self, operation: Mapping[str, Any]) -> str:
        consumes = operation.get("consumes") or self.spec.document.get("consumes") or []
        return _pick_media(list(consumes)) or JSON_MEDIA

    def _param_schema(self, param: Mapping[str, Any]) -> InputSpec:
        if "schema" in param:
            return self.schema(param["schema"], ())
        if "content" in param:  # OpenAPI 3 parameter with a media-typed schema
            content = param["content"]
            first: Any = next(iter(content.values()), {})
            return self.schema(first.get("schema") or {}, ())
        # Swagger 2.0: type/format/items/... live on the parameter itself
        return self.schema(
            {k: v for k, v in param.items() if k not in ("name", "in", "required", "description")},
            (),
        )

    def schema(self, node: Any, stack: Sequence[str]) -> InputSpec:
        """Convert a (possibly referencing) schema; ``stack`` holds the refs being expanded."""
        if not isinstance(node, Mapping):
            return AnyInput()
        if "$ref" in node:
            ref = str(node["$ref"])
            name = ref.rsplit("/", 1)[-1]
            if ref in stack:
                return RecursiveInput(schema_name=name)
            try:
                target = self.spec.resolve(node)
            except SpecError:
                return AnyInput()
            converted = self.schema(target, [*stack, ref])
            if isinstance(converted, ObjectInput) and converted.schema_name is None:
                return ObjectInput(
                    properties=converted.properties,
                    additional=converted.additional,
                    schema_name=name,
                    nullable=converted.nullable,
                )
            return converted

        nullable = bool(node.get("nullable") or node.get("x-nullable"))
        kind = node.get("type")
        if isinstance(kind, list):  # OpenAPI 3.1: type: [string, "null"]
            nullable = nullable or "null" in kind
            kinds = [k for k in kind if k != "null"]
            kind = kinds[0] if len(kinds) == 1 else None

        if "enum" in node and isinstance(node["enum"], list):
            values = tuple(v for v in node["enum"] if v is not None)
            return EnumInput(values=values, nullable=nullable or None in node["enum"])
        if "allOf" in node:
            return self._all_of(node, stack, nullable)
        for key, exclusive in (("oneOf", True), ("anyOf", False)):
            if isinstance(node.get(key), list):
                return ChoiceInput(
                    options=tuple(self.schema(o, stack) for o in node[key]),
                    exclusive=exclusive,
                    nullable=nullable,
                )

        if kind is None:
            if "properties" in node or "additionalProperties" in node:
                kind = "object"
            elif "items" in node:
                kind = "array"
        if kind == "boolean":
            return BooleanInput(nullable=nullable)
        if kind == "integer":
            return IntegerInput(
                minimum=_int(node.get("minimum")),
                maximum=_int(node.get("maximum")),
                exclusive_minimum=node.get("exclusiveMinimum") is True,
                exclusive_maximum=node.get("exclusiveMaximum") is True,
                multiple_of=_int(node.get("multipleOf")),
                format=node.get("format"),
                nullable=nullable,
            )
        if kind == "number":
            return NumberInput(
                minimum=_num(node.get("minimum")),
                maximum=_num(node.get("maximum")),
                exclusive_minimum=node.get("exclusiveMinimum") is True,
                exclusive_maximum=node.get("exclusiveMaximum") is True,
                format=node.get("format"),
                nullable=nullable,
            )
        if kind in ("string", "file"):
            return StringInput(
                min_length=_int(node.get("minLength")),
                max_length=_int(node.get("maxLength")),
                pattern=node.get("pattern"),
                format="binary" if kind == "file" else node.get("format"),
                nullable=nullable,
            )
        if kind == "array":
            return ArrayInput(
                item=self.schema(node.get("items") or {}, stack),
                min_items=_int(node.get("minItems")),
                max_items=_int(node.get("maxItems")),
                unique_items=bool(node.get("uniqueItems")),
                nullable=nullable,
            )
        if kind == "object":
            required = set(node.get("required") or [])
            properties = tuple(
                Property(str(name), self.schema(sub, stack), name in required)
                for name, sub in (node.get("properties") or {}).items()
            )
            extra = node.get("additionalProperties")
            additional = (
                self.schema(extra, stack)
                if isinstance(extra, Mapping)
                else AnyInput()
                if extra is True
                else None
            )
            return ObjectInput(properties=properties, additional=additional, nullable=nullable)
        return AnyInput(nullable=nullable)

    def _all_of(self, node: Mapping[str, Any], stack: Sequence[str], nullable: bool) -> InputSpec:
        parts = [self.schema(p, stack) for p in node["allOf"]]
        objects = [p for p in parts if isinstance(p, ObjectInput)]
        if len(objects) != len(parts):
            return (
                parts[0] if len(parts) == 1 else ChoiceInput(options=tuple(parts), exclusive=False)
            )
        merged: dict[str, Property] = {}
        for part in objects:
            for prop in part.properties:
                merged[prop.name] = prop
        name = next((p.schema_name for p in objects if p.schema_name), None)
        return ObjectInput(properties=tuple(merged.values()), schema_name=name, nullable=nullable)


def _pick_media(media_types: list[str]) -> str | None:
    """JSON first, then forms, then whatever is documented first."""
    for media in media_types:
        if media.split(";")[0].strip().endswith("json"):
            return media
    for media in media_types:
        if media in FORM_MEDIA:
            return media
    return media_types[0] if media_types else None


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
