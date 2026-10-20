"""Test coverage criteria for RESTful APIs (Martin-Lopez, Segura, Ruiz-Cortés, A-TEST 2019).

Ten black-box criteria, computed from the proxy recording and the OpenAPI document:

input  path · operation · parameter · parameter value · content-type · operation flow
output status code class · status code · response body properties · content-type

and the cumulative Test Coverage Levels TCL1..TCL7 (§4). Every criterion reports
``covered``, ``total`` and ``ratio`` (``None`` when nothing is measurable, e.g. no enum
parameters). Choices the paper leaves open are made explicit:

* operation coverage here is "a request was sent" (the paper's definition); the 2xx-based
  definition of RESTgym/WFC is ``operations.operation_success_coverage``;
* status code classes: correct = 2xx, erroneous = 4xx or 5xx (the paper's case study);
* status code coverage counts documented numeric codes; ``default`` and ranges such as
  ``4XX`` are left out of the denominator;
* operation flows are inferred from black-box traffic: a flow counts when its second step
  was answered after a successful create of the same resource type (time order);
* response bodies larger than ``proxy.max_body_bytes`` were stored truncated and are not
  parsed; their properties count as not obtained, and the number of such bodies is
  reported.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from restgen.coverage.models import ratio
from restgen.openapi import HTTP_METHODS, OpenApiSpec
from restgen.representation.inputs import BooleanInput, EnumInput, InputSpec
from restgen.representation.resources import segments
from restgen.representation.templates import Location, OperationTemplate, build_templates
from restgen.traffic.models import HttpInteraction

# Test Coverage Levels: criteria that must all be at 100 % (cumulatively) for each level.
TCL_LEVELS: tuple[tuple[str, ...], ...] = (
    ("path",),
    ("operation",),
    ("input_content_type", "output_content_type"),
    ("parameter", "status_code_class"),
    ("parameter_value", "status_code"),
    ("response_body_properties",),
    ("operation_flow",),
)
MAX_PROPERTY_DEPTH = 6


@dataclass(frozen=True)
class Criterion:
    covered: frozenset[str]
    total: frozenset[str]

    @property
    def ratio(self) -> float | None:
        return ratio(len(self.covered & self.total), len(self.total))

    def summary(self) -> dict[str, Any]:
        return {
            "covered": len(self.covered & self.total),
            "total": len(self.total),
            "ratio": self.ratio,
            "missing": sorted(self.total - self.covered)[:50],
        }


def coverage_criteria(
    spec: OpenApiSpec,
    interactions: Sequence[HttpInteraction],
    max_body_bytes: int,
) -> dict[str, Any]:
    templates = {t.key: t for t in build_templates(spec)}
    observed = [
        (template, interaction)
        for interaction in interactions
        if (op := spec.match(interaction.method, interaction.target).operation) is not None
        and (template := templates.get(op.key)) is not None
    ]
    criteria = {
        "path": _paths(templates.values(), observed),
        "operation": Criterion(frozenset(t.key for t, _ in observed), frozenset(templates)),
        "parameter": _parameters(templates.values(), observed),
        "parameter_value": _parameter_values(templates.values(), observed),
        "input_content_type": _input_content_types(spec, templates.values(), observed),
        "operation_flow": _flows(templates.values(), observed),
        "status_code_class": _status_classes(templates.values(), observed),
        "status_code": _status_codes(templates.values(), observed),
        "response_body_properties": _response_properties(
            spec, templates.values(), observed, max_body_bytes
        ),
        "output_content_type": _output_content_types(spec, templates.values(), observed),
    }
    level = 0
    for index, names in enumerate(TCL_LEVELS, start=1):
        # a criterion with nothing to cover (ratio None) does not block a level
        if all(criteria[name].ratio in (None, 1.0) for name in names):
            level = index
        else:
            break
    truncated = sum(1 for _, i in observed if i.response_body_size > max_body_bytes)
    return {
        **{name: criterion.summary() for name, criterion in criteria.items()},
        "test_coverage_level": level,
        "truncated_response_bodies": truncated,
    }


# -- input criteria --------------------------------------------------------------------


def _paths(
    templates: Iterable[OperationTemplate], observed: Sequence[tuple[OperationTemplate, Any]]
) -> Criterion:
    return Criterion(frozenset(t.path for t, _ in observed), frozenset(t.path for t in templates))


def _query(interaction: HttpInteraction) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for key, value in parse_qsl(urlsplit(interaction.target).query, keep_blank_values=True):
        values.setdefault(key, []).append(value)
    return values


def _cookies(interaction: HttpInteraction) -> dict[str, str]:
    raw = interaction.request_headers.get("cookie", "")
    pairs = (part.strip().split("=", 1) for part in raw.split(";") if "=" in part)
    return {name: value for name, value in pairs}


def _path_values(template: OperationTemplate, interaction: HttpInteraction) -> dict[str, str]:
    concrete = segments(unquote(urlsplit(interaction.target).path))
    pattern = segments(template.base_path + template.path)
    values = {}
    if len(concrete) == len(pattern):
        for part, value in zip(pattern, concrete, strict=True):
            if part.startswith("{") and part.endswith("}"):
                values[part[1:-1]] = value
    return values


def _sent(template: OperationTemplate, interaction: HttpInteraction) -> dict[str, list[str]]:
    """Inputs present in a request, keyed by position key (``query:limit``)."""
    sent: dict[str, list[str]] = {}
    for name, value in _path_values(template, interaction).items():
        sent[f"path:{name}"] = [value]
    for name, values in _query(interaction).items():
        sent[f"query:{name}"] = values
    headers = {k.lower(): v for k, v in interaction.request_headers.items()}
    for position in template.at(Location.HEADER):
        if position.name.lower() in headers:
            sent[position.key] = [headers[position.name.lower()]]
    for name, value in _cookies(interaction).items():
        sent[f"cookie:{name}"] = [value]
    if interaction.request_body_size > 0:
        sent["body:body"] = [interaction.request_body]
    return sent


def _parameters(
    templates: Iterable[OperationTemplate], observed: Sequence[tuple[OperationTemplate, Any]]
) -> Criterion:
    total = {f"{t.key} {p.key}" for t in templates for p in t.inputs}
    covered = {f"{t.key} {key}" for t, interaction in observed for key in _sent(t, interaction)}
    return Criterion(frozenset(covered), frozenset(total))


def _finite_values(spec: InputSpec) -> list[str] | None:
    if isinstance(spec, BooleanInput):
        return ["true", "false"]
    if isinstance(spec, EnumInput):
        return [_text(v) for v in spec.values]
    return None


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _parameter_values(
    templates: Iterable[OperationTemplate], observed: Sequence[tuple[OperationTemplate, Any]]
) -> Criterion:
    total: set[str] = set()
    for template in templates:
        for position in template.inputs:
            if position.location is Location.BODY:
                continue  # the paper's parameters with finite domains: not request bodies
            values = _finite_values(position.spec)
            if values:
                total.update(f"{template.key} {position.key}={v}" for v in values)
    covered: set[str] = set()
    for template, interaction in observed:
        for key, values in _sent(template, interaction).items():
            for value in values:
                for candidate in (value, value.lower()):
                    covered.add(f"{template.key} {key}={candidate}")
    return Criterion(frozenset(covered), frozenset(total))


def _declared_request_media(spec: OpenApiSpec, template: OperationTemplate) -> set[str]:
    operation = _raw_operation(spec, template)
    if operation is None:
        return set()
    body = spec.resolve(operation.get("requestBody"))
    if isinstance(body, Mapping):
        return {_media(m) for m in (body.get("content") or {})}
    if template.body is not None:  # Swagger 2.0 body/formData
        consumes = operation.get("consumes") or spec.document.get("consumes") or []
        return {_media(m) for m in consumes} or (
            {_media(template.media_type)} if template.media_type else set()
        )
    return set()


def _input_content_types(
    spec: OpenApiSpec,
    templates: Iterable[OperationTemplate],
    observed: Sequence[tuple[OperationTemplate, HttpInteraction]],
) -> Criterion:
    total = {f"{t.key} {m}" for t in templates for m in _declared_request_media(spec, t)}
    covered = {
        f"{t.key} {_media(i.request_headers.get('content-type', ''))}"
        for t, i in observed
        if i.request_body_size > 0 and i.request_headers.get("content-type")
    }
    return Criterion(frozenset(covered), frozenset(total))


def _flows(
    templates: Iterable[OperationTemplate],
    observed: Sequence[tuple[OperationTemplate, HttpInteraction]],
) -> Criterion:
    """Martin-Lopez's simplified Arcuri flows for every creatable resource."""
    by_shape: dict[tuple[str, str], str] = {}
    for template in templates:
        by_shape[(template.method, _shape(template.path))] = template.key
    total: set[str] = set()
    steps: dict[str, tuple[str, str]] = {}  # flow -> (create op, second op)
    for template in templates:
        if template.method not in ("POST", "PUT"):
            continue
        parts = segments(template.path)
        if template.method == "POST" and parts and not _is_param(parts[-1]):
            collection, element = template.path, _shape(template.path) + "/{}"
        elif parts and _is_param(parts[-1]):
            collection, element = "/" + "/".join(parts[:-1]), _shape(template.path)
        else:
            continue
        second = {
            "read one": ("GET", element),
            "read all": ("GET", _shape(collection)),
            "update": ("PUT", element),
            "delete": ("DELETE", element),
        }
        for name, (method, shape) in second.items():
            target = by_shape.get((method, shape)) or (
                by_shape.get(("PATCH", shape)) if name == "update" else None
            )
            if target is not None and target != template.key:
                flow = f"{template.key} -> {name} ({target})"
                total.add(flow)
                steps[flow] = (template.key, target)
    created_at: dict[str, float] = {}
    covered: set[str] = set()
    for template, interaction in sorted(observed, key=lambda pair: pair[1].started_at):
        if interaction.status is not None and 200 <= interaction.status < 300:
            created_at.setdefault(template.key, interaction.started_at)
        if interaction.status is None:
            continue
        for flow, (create, follow_up) in steps.items():
            if follow_up == template.key and create in created_at:
                covered.add(flow)
    return Criterion(frozenset(covered), frozenset(total))


# -- output criteria -------------------------------------------------------------------


def _status_classes(
    templates: Iterable[OperationTemplate],
    observed: Sequence[tuple[OperationTemplate, HttpInteraction]],
) -> Criterion:
    total = {f"{t.key} {c}" for t in templates for c in ("correct", "erroneous")}
    covered = set()
    for template, interaction in observed:
        status = interaction.status
        if status is None:
            continue
        if 200 <= status < 300:
            covered.add(f"{template.key} correct")
        elif 400 <= status < 600:
            covered.add(f"{template.key} erroneous")
    return Criterion(frozenset(covered), frozenset(total))


def _status_codes(
    templates: Iterable[OperationTemplate],
    observed: Sequence[tuple[OperationTemplate, HttpInteraction]],
) -> Criterion:
    total = {f"{t.key} {code}" for t in templates for code in t.responses if code.isdigit()}
    covered = {f"{t.key} {i.status}" for t, i in observed if i.status is not None}
    return Criterion(frozenset(covered), frozenset(total))


def _response_schemas(
    spec: OpenApiSpec, template: OperationTemplate
) -> list[tuple[str, Mapping[str, Any]]]:
    """(status code, JSON schema) of every documented response with a body schema."""
    operation = _raw_operation(spec, template)
    if operation is None:
        return []
    schemas: list[tuple[str, Mapping[str, Any]]] = []
    for code, raw in (operation.get("responses") or {}).items():
        response = spec.resolve(raw)
        if not isinstance(response, Mapping):
            continue
        if "content" in response:  # OpenAPI 3
            for media, item in (response.get("content") or {}).items():
                if (
                    _media(media).endswith("json")
                    and isinstance(item, Mapping)
                    and "schema" in item
                ):
                    schemas.append((str(code), spec.json_schema(item["schema"])))
        elif "schema" in response:  # Swagger 2.0
            schemas.append((str(code), spec.json_schema(response["schema"])))
    return schemas


def _property_paths(schema: Any, prefix: str = "", depth: int = 0) -> set[str]:
    if not isinstance(schema, Mapping) or depth > MAX_PROPERTY_DEPTH:
        return set()
    paths: set[str] = set()
    for key in ("allOf", "oneOf", "anyOf"):
        for part in schema.get(key) or []:
            paths |= _property_paths(part, prefix, depth)
    if isinstance(schema.get("items"), Mapping):
        paths |= _property_paths(schema["items"], prefix + "[]", depth + 1)
    for name, sub in (schema.get("properties") or {}).items():
        path = f"{prefix}.{name}" if prefix else str(name)
        paths.add(path)
        paths |= _property_paths(sub, path, depth + 1)
    return paths


def _present_paths(value: Any, prefix: str = "", depth: int = 0) -> set[str]:
    if depth > MAX_PROPERTY_DEPTH:
        return set()
    paths: set[str] = set()
    if isinstance(value, dict):
        for name, sub in value.items():
            path = f"{prefix}.{name}" if prefix else str(name)
            paths.add(path)
            paths |= _present_paths(sub, path, depth + 1)
    elif isinstance(value, list):
        for item in value:
            paths |= _present_paths(item, prefix + "[]", depth + 1)
    return paths


def _response_properties(
    spec: OpenApiSpec,
    templates: Iterable[OperationTemplate],
    observed: Sequence[tuple[OperationTemplate, HttpInteraction]],
    max_body_bytes: int,
) -> Criterion:
    total: set[str] = set()
    expected: set[tuple[str, str]] = set()
    for template in templates:
        for code, schema in _response_schemas(spec, template):
            expected.add((template.key, code))
            total.update(f"{template.key} {code} {p}" for p in _property_paths(schema))
    covered: set[str] = set()
    for template, interaction in observed:
        if interaction.status is None or interaction.response_body_size > max_body_bytes:
            continue
        code = str(interaction.status)
        if (template.key, code) not in expected:
            continue
        try:
            body = json.loads(interaction.response_body)
        except (json.JSONDecodeError, ValueError):
            continue
        covered.update(f"{template.key} {code} {p}" for p in _present_paths(body))
    return Criterion(frozenset(covered), frozenset(total))


def _declared_response_media(spec: OpenApiSpec, template: OperationTemplate) -> set[str]:
    operation = _raw_operation(spec, template)
    if operation is None:
        return set()
    media: set[str] = set()
    has_schema = False
    for raw in (operation.get("responses") or {}).values():
        response = spec.resolve(raw)
        if isinstance(response, Mapping):
            media.update(_media(m) for m in (response.get("content") or {}))
            has_schema = has_schema or "schema" in response
    if has_schema:  # Swagger 2.0: produces applies to responses with a body
        media.update(
            _media(m) for m in (operation.get("produces") or spec.document.get("produces") or [])
        )
    return media


def _output_content_types(
    spec: OpenApiSpec,
    templates: Iterable[OperationTemplate],
    observed: Sequence[tuple[OperationTemplate, HttpInteraction]],
) -> Criterion:
    total = {f"{t.key} {m}" for t in templates for m in _declared_response_media(spec, t)}
    covered = {
        f"{t.key} {_media(i.response_headers.get('content-type', ''))}"
        for t, i in observed
        if i.response_headers.get("content-type")
    }
    return Criterion(frozenset(covered), frozenset(total))


# -- helpers ---------------------------------------------------------------------------


def _raw_operation(spec: OpenApiSpec, template: OperationTemplate) -> Mapping[str, Any] | None:
    item = spec.resolve(spec.document["paths"].get(template.path))
    if not isinstance(item, Mapping):
        return None
    operation = item.get(template.method.lower())
    if template.method.lower() not in HTTP_METHODS or not isinstance(operation, Mapping):
        return None
    return operation


def _media(value: str | None) -> str:
    return (value or "").split(";")[0].strip().lower()


def _is_param(part: str) -> bool:
    return part.startswith("{") and part.endswith("}")


def _shape(path: str) -> str:
    return "/" + "/".join("{}" if _is_param(p) else p for p in segments(path))
