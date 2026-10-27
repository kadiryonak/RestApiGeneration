"""Resource relationships derived from URI structure and HTTP semantics.

REST places resources in hierarchical URIs: ``/users/{id}`` is an element of the
collection ``/users``. To call ``GET /users/{id}`` with an id that exists, a test first
needs a resource created by ``POST /users`` (or ``POST``/``PUT /users/{id}`` when the
client chooses the id). Resources created by "action" endpoints
(``POST /products/{p}/constraints/excludes`` → ``/constraints/{id}``) cannot be read off
the URIs and stay unresolvable here. These relations
are read off the document only (no execution), so they are *candidates*: a method may
confirm or reject them at run time (Arcuri, TOSEM 2019; Zhang et al., EMSE 2021).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from restgen.core.representation.templates import Location, OperationTemplate

_PARAM = re.compile(r"^\{([^{}]+)\}$")


@dataclass(frozen=True)
class ResourceDependency:
    operation: str  # the operation that needs an existing resource
    parameter: str  # its path parameter that identifies the resource
    collection: str  # path template of the collection the resource belongs to
    # operations that may create it: POST on the collection (server-chosen id),
    # POST or PUT on the element (client-chosen id, e.g. a name in the URL)
    creators: tuple[str, ...]

    @property
    def resolvable(self) -> bool:
        return bool(self.creators)


def segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def resource_dependencies(templates: Sequence[OperationTemplate]) -> list[ResourceDependency]:
    keys = [t.key for t in templates]
    dependencies = []
    for template in templates:
        parts = segments(template.path)
        path_params = {p.name for p in template.at(Location.PATH)}
        for index, part in enumerate(parts):
            match = _PARAM.match(part)
            if not match or match.group(1) not in path_params:
                continue
            # creating the element itself is not a dependency on it
            element = "/" + "/".join(parts[: index + 1])
            if template.method in ("POST", "PUT") and element == _normal(template.path):
                continue
            collection = "/" + "/".join(parts[:index])
            creators = tuple(
                found
                for wanted in (f"POST {collection}", f"POST {element}", f"PUT {element}")
                if (found := _find(keys, wanted)) is not None
            )
            dependencies.append(
                ResourceDependency(template.key, match.group(1), collection or "/", creators)
            )
    return dependencies


def summarize(templates: Sequence[OperationTemplate]) -> dict[str, Any]:
    """Structural characteristics of an API (for benchmark description, cf. PRAB)."""
    dependencies = resource_dependencies(templates)
    kinds: dict[str, int] = {}
    formats: dict[str, int] = {}
    locations: dict[str, int] = {}
    depth = 0
    for template in templates:
        for position in template.inputs:
            locations[position.location.value] = locations.get(position.location.value, 0) + 1
            depth = max(depth, _depth(position.spec))
            for spec in position.spec.walk():
                kinds[spec.kind] = kinds.get(spec.kind, 0) + 1
                fmt = getattr(spec, "format", None)
                if fmt:
                    formats[fmt] = formats.get(fmt, 0) + 1
    methods: dict[str, int] = {}
    for template in templates:
        methods[template.method] = methods.get(template.method, 0) + 1
    return {
        "operations": len(templates),
        "methods": dict(sorted(methods.items())),
        "input_positions": locations,
        "scalar_positions": sum(t.scalar_count() for t in templates),
        "max_nesting_depth": depth,
        "spec_kinds": dict(sorted(kinds.items())),
        "formats": dict(sorted(formats.items())),
        "operations_with_body": sum(1 for t in templates if t.body is not None),
        "body_media_types": sorted({t.media_type for t in templates if t.media_type}),
        "resource_dependencies": len(dependencies),
        "unresolvable_dependencies": sorted(
            f"{d.operation} ({d.parameter})" for d in dependencies if not d.resolvable
        ),
    }


def _depth(spec: Any, level: int = 1) -> int:
    children = spec.children()
    return level if not children else max(_depth(child, level + 1) for child in children)


def _normal(path: str) -> str:
    return "/" + "/".join(segments(path))


def _shape(path: str) -> str:
    """Path with parameter names erased: /users/{id} and /users/{userId} are one resource."""
    return "/" + "/".join("{}" if _PARAM.match(s) else s for s in segments(path))


def _find(keys: Iterable[str], wanted: str) -> str | None:
    """The actual operation key matching ``wanted`` up to parameter names and slashes."""
    method, path = wanted.split(" ", 1)
    for key in keys:
        key_method, key_path = key.split(" ", 1)
        if key_method == method and _shape(key_path) == _shape(path):
            return key
    return None
