"""OpenAPI documents: operations (HTTP method + path template) and request schemas.

An *operation* is the pair (method, path template), e.g. ``GET /users/{id}`` and
``DELETE /users/{id}`` are two operations on the same path.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
import yaml

from restgen.errors import SpecError

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
# Recursive schemas are cut off at this depth and replaced by an unconstrained schema.
MAX_REF_DEPTH = 8
_PARAM = re.compile(r"\{([^{}/]+)\}")
# Keywords OpenAPI adds to JSON Schema that a JSON Schema validator/generator rejects.
_OPENAPI_ONLY = (
    "nullable",
    "discriminator",
    "readOnly",
    "writeOnly",
    "xml",
    "externalDocs",
    "example",
    "deprecated",
)


@dataclass(frozen=True)
class Parameter:
    name: str
    location: str  # path | query | header | cookie
    required: bool
    schema: Mapping[str, Any]


@dataclass(frozen=True)
class Operation:
    method: str  # upper case
    path: str  # template as written in the document, e.g. /users/{id}
    operation_id: str | None
    parameters: tuple[Parameter, ...]
    json_body: Mapping[str, Any] | None
    body_required: bool
    responses: tuple[str, ...]  # documented status codes / ranges / "default"

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"


@dataclass(frozen=True)
class MatchedRequest:
    operation: Operation | None
    path: str  # concrete path without the API base path


class OpenApiSpec:
    """A loaded OpenAPI 3.x (or Swagger 2.0) document."""

    def __init__(self, document: Mapping[str, Any]) -> None:
        if not isinstance(document.get("paths"), Mapping):
            raise SpecError("document has no 'paths' object")
        self._doc = document

    @classmethod
    def load(cls, source: str | Path, timeout: float = 30.0) -> OpenApiSpec:
        """Load from a file path or an http(s) URL; JSON and YAML are both accepted."""
        text: str
        if isinstance(source, str) and source.startswith(("http://", "https://")):
            try:
                response = httpx.get(source, timeout=timeout, follow_redirects=True)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise SpecError(f"cannot fetch OpenAPI document {source}: {exc}") from exc
            text = response.text
        else:
            try:
                text = Path(source).read_text(encoding="utf-8")
            except OSError as exc:
                raise SpecError(f"cannot read OpenAPI document {source}: {exc}") from exc
        return cls(parse_document(text))

    @property
    def document(self) -> Mapping[str, Any]:
        return self._doc

    @property
    def version(self) -> str:
        return str(self._doc.get("openapi") or self._doc.get("swagger") or "unknown")

    @cached_property
    def base_path(self) -> str:
        """Path prefix every operation path is relative to ('' when none)."""
        if "swagger" in self._doc:
            base = str(self._doc.get("basePath") or "")
        else:
            servers = self._doc.get("servers") or []
            url = str(servers[0].get("url", "")) if servers else ""
            base = urlsplit(url).path if "://" in url else url
        base = base.rstrip("/")
        return "" if base in ("", "/") else base

    @cached_property
    def operations(self) -> tuple[Operation, ...]:
        found: list[Operation] = []
        for path, item in self._doc["paths"].items():
            item = self.resolve(item)
            if not isinstance(item, Mapping):
                continue
            shared = item.get("parameters") or []
            for method in HTTP_METHODS:
                operation = item.get(method)
                if isinstance(operation, Mapping):
                    found.append(self._operation(method, str(path), operation, shared))
        return tuple(found)

    def operation(self, key: str) -> Operation:
        for operation in self.operations:
            if operation.key == key:
                return operation
        raise SpecError(f"no such operation: {key}")

    @cached_property
    def _matchers(self) -> list[tuple[re.Pattern[str], int, Operation]]:
        matchers = []
        for operation in self.operations:
            pattern = _template_regex(operation.path)
            literal_chars = len(_PARAM.sub("", operation.path))
            matchers.append((pattern, literal_chars, operation))
        # More literal characters first: /users/me must win over /users/{id}.
        matchers.sort(key=lambda entry: -entry[1])
        return matchers

    def match(self, method: str, raw_path: str) -> MatchedRequest:
        """Map a concrete request (method + URL path) to its documented operation."""
        path = unquote(urlsplit(raw_path).path) or "/"
        if self.base_path and (path == self.base_path or path.startswith(self.base_path + "/")):
            path = path[len(self.base_path) :] or "/"
        if len(path) > 1:
            path = path.rstrip("/")
        method = method.upper()
        for pattern, _, operation in self._matchers:
            if operation.method == method and pattern.fullmatch(path):
                return MatchedRequest(operation, path)
        return MatchedRequest(None, path)

    # -- schemas ------------------------------------------------------------------

    def resolve(self, node: Any) -> Any:
        """Resolve one level of local ``$ref`` (``#/...``)."""
        seen: set[str] = set()
        while isinstance(node, Mapping) and "$ref" in node:
            ref = str(node["$ref"])
            if ref in seen:
                raise SpecError(f"circular $ref: {ref}")
            seen.add(ref)
            node = self._pointer(ref)
        return node

    def json_schema(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        """A self-contained JSON Schema: local refs inlined, OpenAPI keywords translated."""
        converted = self._inline(schema, 0)
        return converted if isinstance(converted, dict) else {}

    def _pointer(self, ref: str) -> Any:
        if not ref.startswith("#/"):
            raise SpecError(f"only local $ref values are supported: {ref}")
        node: Any = self._doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, Mapping) or part not in node:
                raise SpecError(f"unresolvable $ref: {ref}")
            node = node[part]
        return node

    def _inline(self, node: Any, depth: int) -> Any:
        if isinstance(node, list):
            return [self._inline(item, depth) for item in node]
        if not isinstance(node, Mapping):
            return copy.deepcopy(node)
        if "$ref" in node:
            if depth >= MAX_REF_DEPTH:
                return {}
            return self._inline(self._pointer(str(node["$ref"])), depth + 1)
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key in _OPENAPI_ONLY:
                continue
            if key in ("properties", "patternProperties", "$defs", "definitions"):
                result[key] = {name: self._inline(sub, depth) for name, sub in value.items()}
            else:
                result[key] = self._inline(value, depth)
        if node.get("nullable") is True:
            result = {"anyOf": [result, {"type": "null"}]}
        return result

    def _operation(
        self, method: str, path: str, operation: Mapping[str, Any], shared: list[Any]
    ) -> Operation:
        parameters: dict[tuple[str, str], Parameter] = {}
        json_body: Mapping[str, Any] | None = None
        body_required = False
        for raw in [*shared, *(operation.get("parameters") or [])]:
            param = self.resolve(raw)
            if not isinstance(param, Mapping) or "name" not in param or "in" not in param:
                continue
            location = str(param["in"])
            if location == "body":  # Swagger 2.0
                json_body = self.json_schema(param.get("schema") or {})
                body_required = bool(param.get("required", False))
                continue
            if location == "formData":
                continue
            schema = param.get("schema")
            if schema is None:  # Swagger 2.0 keeps type/format on the parameter itself
                schema = {
                    k: v
                    for k, v in param.items()
                    if k
                    in (
                        "type",
                        "format",
                        "enum",
                        "items",
                        "minimum",
                        "maximum",
                        "pattern",
                        "minLength",
                        "maxLength",
                    )
                }
            parameters[(str(param["name"]), location)] = Parameter(
                name=str(param["name"]),
                location=location,
                required=bool(param.get("required", location == "path")),
                schema=self.json_schema(schema),
            )
        request_body = self.resolve(operation.get("requestBody"))
        if isinstance(request_body, Mapping):
            content = request_body.get("content") or {}
            media = next((m for m in content if m.split(";")[0].strip().endswith("json")), None)
            if media is not None:
                json_body = self.json_schema(content[media].get("schema") or {})
                body_required = bool(request_body.get("required", False))
        return Operation(
            method=method.upper(),
            path=path,
            operation_id=operation.get("operationId"),
            parameters=tuple(parameters.values()),
            json_body=json_body,
            body_required=body_required,
            responses=tuple(str(code) for code in (operation.get("responses") or {})),
        )


def parse_document(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SpecError(f"OpenAPI document is neither JSON nor YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError("OpenAPI document must be an object")
    return data


def _template_regex(template: str) -> re.Pattern[str]:
    template = template.rstrip("/") or "/"
    parts = []
    position = 0
    for match in _PARAM.finditer(template):
        parts.append(re.escape(template[position : match.start()]))
        parts.append("[^/]+")
        position = match.end()
    parts.append(re.escape(template[position:]))
    return re.compile("".join(parts))
