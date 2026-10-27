"""One HTTP call of a test case: an operation template plus a value for its inputs.

The template is the fixed part (method, path template, media type); the values are the
variable part. :meth:`HttpAction.to_request` renders both into the concrete request,
which is the only form an executor needs.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from restgen.core.representation.templates import Location, OperationTemplate
from restgen.core.representation.values import (
    ABSENT,
    OptionalValue,
    ResponseRef,
    Value,
    placeholder,
)


@dataclass(frozen=True)
class HttpRequest:
    """A fully rendered request. ``body`` is :data:`ABSENT` when nothing is sent."""

    method: str
    path: str  # base path + path template with the path parameters filled in
    query: tuple[tuple[str, str], ...] = ()
    headers: tuple[tuple[str, str], ...] = ()
    cookies: tuple[tuple[str, str], ...] = ()
    media_type: str | None = None
    body: Any = ABSENT


@dataclass
class HttpAction:
    """``parameters`` maps :attr:`InputPosition.key` (``"path:user_id"``,
    ``"query:limit"``, ...) to a value; ``body`` is the request body's value."""

    operation: OperationTemplate
    parameters: dict[str, Value] = field(default_factory=dict)
    body: Value | None = None

    def __post_init__(self) -> None:
        known = {i.key for i in self.operation.inputs if i.location is not Location.BODY}
        unknown = set(self.parameters) - known
        if unknown:
            raise ValueError(f"{self.operation.key} has no input(s) {sorted(unknown)}")
        if self.body is not None and self.operation.body is None:
            raise ValueError(f"{self.operation.key} takes no request body")

    @classmethod
    def placeholder(cls, operation: OperationTemplate) -> HttpAction:
        """Every input filled with :func:`~restgen.core.representation.values.placeholder`;
        optional parameters and an optional body are absent."""
        parameters: dict[str, Value] = {}
        body: Value | None = None
        for position in operation.inputs:
            value = placeholder(position.spec)
            if not position.required:
                value = OptionalValue(value, present=False)
            if position.location is Location.BODY:
                body = value
            else:
                parameters[position.key] = value
        return cls(operation, parameters, body)

    def values(self) -> Iterator[Value]:
        """Every value of this action, nested ones included."""
        for value in self.parameters.values():
            yield from value.walk()
        if self.body is not None:
            yield from self.body.walk()

    def references(self) -> Iterator[ResponseRef]:
        return (v for v in self.values() if isinstance(v, ResponseRef))

    def to_request(self, responses: Sequence[Any] = ()) -> HttpRequest:
        """Render with ``responses`` = parsed bodies of the earlier actions, in order."""
        path = self.operation.path
        grouped: dict[Location, list[tuple[str, str]]] = {
            Location.QUERY: [],
            Location.HEADER: [],
            Location.COOKIE: [],
        }
        for position in self.operation.inputs:
            value = self.parameters.get(position.key)
            if value is None or position.location is Location.BODY:
                continue
            rendered = value.render(responses)
            if rendered is ABSENT:
                continue
            if position.location is Location.PATH:
                path = path.replace(f"{{{position.name}}}", quote(_text(rendered), safe=""))
            else:
                items = rendered if isinstance(rendered, list) else [rendered]
                grouped[position.location].extend((position.name, _text(i)) for i in items)
        body = self.body.render(responses) if self.body is not None else ABSENT
        return HttpRequest(
            method=self.operation.method,
            path=self.operation.base_path.rstrip("/") + path,
            query=tuple(grouped[Location.QUERY]),
            headers=tuple(grouped[Location.HEADER]),
            cookies=tuple(grouped[Location.COOKIE]),
            media_type=self.operation.media_type if body is not ABSENT else None,
            body=body,
        )

    def copy(self) -> HttpAction:
        return HttpAction(
            self.operation,
            {key: value.copy() for key, value in self.parameters.items()},
            self.body.copy() if self.body is not None else None,
        )

    def describe(self) -> dict[str, Any]:
        data: dict[str, Any] = {"operation": self.operation.key}
        for key, value in self.parameters.items():
            described = value.describe()
            if described is not ABSENT:
                data[key] = described
        if self.body is not None and (described := self.body.describe()) is not ABSENT:
            data["body"] = described
        return data


def _text(value: Any) -> str:
    """A scalar as it appears in a URL or header: JSON spelling for true/false/null."""
    if isinstance(value, str):
        return value
    return json.dumps(value)
