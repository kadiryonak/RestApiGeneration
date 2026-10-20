"""Input specifications: what may vary in a request, and within which documented limits.

This layer is method-neutral. It describes the API (types, constraints, nesting) as the
OpenAPI document states it and holds no values and no search concepts: an ABC food
source, an evolutionary individual or an LLM prompt are all built *on top of* it by the
method that uses it.

Constraints are exactly the documented ones (``None`` = not constrained). Practical caps
(e.g. "at most 5 array items") are choices of the search method, not facts of the API.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InputSpec:
    """Base class. ``nullable``: JSON null is a documented value."""

    nullable: bool = field(default=False, kw_only=True)

    @property
    def kind(self) -> str:
        return type(self).__name__.removesuffix("Input").lower()

    @property
    def is_leaf(self) -> bool:
        return not self.children()

    def children(self) -> tuple[InputSpec, ...]:
        return ()

    def walk(self) -> Iterator[InputSpec]:
        """This spec and every spec nested in it (depth first)."""
        yield self
        for child in self.children():
            yield from child.walk()

    def leaves(self) -> Iterator[InputSpec]:
        """The scalar positions a concrete value is finally made of."""
        return (spec for spec in self.walk() if spec.is_leaf)

    def describe(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind}
        if self.nullable:
            data["nullable"] = True
        return data


@dataclass(frozen=True)
class BooleanInput(InputSpec):
    pass


@dataclass(frozen=True)
class IntegerInput(InputSpec):
    minimum: int | None = None
    maximum: int | None = None
    exclusive_minimum: bool = False
    exclusive_maximum: bool = False
    multiple_of: int | None = None
    format: str | None = None  # int32 / int64

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            **_present(
                minimum=self.minimum,
                maximum=self.maximum,
                multiple_of=self.multiple_of,
                format=self.format,
            ),
            **_flags(
                exclusive_minimum=self.exclusive_minimum, exclusive_maximum=self.exclusive_maximum
            ),
        }


@dataclass(frozen=True)
class NumberInput(InputSpec):
    minimum: float | None = None
    maximum: float | None = None
    exclusive_minimum: bool = False
    exclusive_maximum: bool = False
    format: str | None = None  # float / double

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            **_present(minimum=self.minimum, maximum=self.maximum, format=self.format),
            **_flags(
                exclusive_minimum=self.exclusive_minimum, exclusive_maximum=self.exclusive_maximum
            ),
        }


@dataclass(frozen=True)
class StringInput(InputSpec):
    """``format`` keeps semantic formats that need valid syntax: date, date-time, time,
    email, uuid, uri, ipv4, ... (``byte`` = base64, ``binary`` = raw bytes)."""

    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    format: str | None = None

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            **_present(
                min_length=self.min_length,
                max_length=self.max_length,
                pattern=self.pattern,
                format=self.format,
            ),
        }


@dataclass(frozen=True)
class EnumInput(InputSpec):
    values: tuple[Any, ...] = ()

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "values": list(self.values)}


@dataclass(frozen=True)
class ArrayInput(InputSpec):
    item: InputSpec = field(default_factory=lambda: AnyInput())
    min_items: int | None = None
    max_items: int | None = None
    unique_items: bool = False

    def children(self) -> tuple[InputSpec, ...]:
        return (self.item,)

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "item": self.item.describe(),
            **_present(min_items=self.min_items, max_items=self.max_items),
            **_flags(unique_items=self.unique_items),
        }


@dataclass(frozen=True)
class Property:
    name: str
    spec: InputSpec
    required: bool


@dataclass(frozen=True)
class ObjectInput(InputSpec):
    """A JSON object with named properties; ``additional`` describes extra keys
    (``additionalProperties``), so an object with no properties is a map."""

    properties: tuple[Property, ...] = ()
    additional: InputSpec | None = None
    schema_name: str | None = None  # components/definitions name, when it has one

    def children(self) -> tuple[InputSpec, ...]:
        extra = (self.additional,) if self.additional is not None else ()
        return tuple(p.spec for p in self.properties) + extra

    @property
    def is_leaf(self) -> bool:
        return False  # an empty object is still a structure, not a scalar

    def describe(self) -> dict[str, Any]:
        data: dict[str, Any] = {**super().describe(), **_present(schema=self.schema_name)}
        data["properties"] = {
            p.name: {**p.spec.describe(), "required": p.required} for p in self.properties
        }
        if self.additional is not None:
            data["additional"] = self.additional.describe()
        return data


@dataclass(frozen=True)
class ChoiceInput(InputSpec):
    """Exactly one (``oneOf``) or at least one (``anyOf``) of the alternatives."""

    options: tuple[InputSpec, ...] = ()
    exclusive: bool = True

    def children(self) -> tuple[InputSpec, ...]:
        return self.options

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "exclusive": self.exclusive,
            "options": [o.describe() for o in self.options],
        }


@dataclass(frozen=True)
class RecursiveInput(InputSpec):
    """A schema that refers back to a type already being described (e.g. a node whose
    ``parent`` is again a node). Recursion is cut here; its value can only be null or
    absent unless a method expands it on purpose."""

    schema_name: str = ""

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "schema": self.schema_name}


@dataclass(frozen=True)
class AnyInput(InputSpec):
    """No type information (empty schema)."""


def _present(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _flags(**values: bool) -> dict[str, bool]:
    return {key: True for key, value in values.items() if value}
