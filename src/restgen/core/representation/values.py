"""Concrete values: one choice for each variable position of a request.

An :mod:`input specification <restgen.core.representation.inputs>` says what *may* be sent;
a value says what *is* sent. Values are mutable so that a method can change them in
place, and :meth:`Value.copy` gives an independent copy. A value keeps the spec it was
made for but is not forced to respect it: sending an out-of-range or wrongly typed value
on purpose is a legitimate test.

Two values are not plain data:

- :class:`OptionalValue` may be *absent* (the property or parameter is not sent at all),
  which is different from sending JSON ``null`` (:class:`NullValue`);
- :class:`ResponseRef` takes its value from the response of an earlier action of the same
  test case (e.g. the ``id`` a ``POST`` returned), so it is only known at execution time.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from restgen.core.representation.inputs import (
    AnyInput,
    ArrayInput,
    BooleanInput,
    ChoiceInput,
    EnumInput,
    InputSpec,
    IntegerInput,
    NumberInput,
    ObjectInput,
    RecursiveInput,
    StringInput,
)
from restgen.errors import UnresolvedReferenceError


class _Absent:
    """Marker rendered by an absent :class:`OptionalValue`: leave the position out."""

    def __repr__(self) -> str:
        return "ABSENT"


ABSENT: Final = _Absent()


class Value(ABC):
    """Base class of every concrete value."""

    spec: InputSpec

    @abstractmethod
    def render(self, responses: Sequence[Any]) -> Any:
        """The JSON value to send (or :data:`ABSENT`). ``responses`` are the parsed JSON
        bodies of the earlier actions of the test case, in order."""

    @abstractmethod
    def copy(self) -> Value:
        """An independent deep copy (specs are immutable and shared)."""

    @abstractmethod
    def describe(self) -> Any:
        """A readable, JSON-serialisable form for logs and reports."""

    def children(self) -> tuple[Value, ...]:
        return ()

    def walk(self) -> Iterator[Value]:
        """This value and every value nested in it (depth first)."""
        yield self
        for child in self.children():
            yield from child.walk()


@dataclass
class BooleanValue(Value):
    spec: BooleanInput
    value: bool

    def render(self, responses: Sequence[Any]) -> Any:
        return self.value

    def copy(self) -> BooleanValue:
        return BooleanValue(self.spec, self.value)

    def describe(self) -> Any:
        return self.value


@dataclass
class IntegerValue(Value):
    spec: IntegerInput
    value: int

    def render(self, responses: Sequence[Any]) -> Any:
        return self.value

    def copy(self) -> IntegerValue:
        return IntegerValue(self.spec, self.value)

    def describe(self) -> Any:
        return self.value


@dataclass
class NumberValue(Value):
    spec: NumberInput
    value: float

    def render(self, responses: Sequence[Any]) -> Any:
        return self.value

    def copy(self) -> NumberValue:
        return NumberValue(self.spec, self.value)

    def describe(self) -> Any:
        return self.value


@dataclass
class StringValue(Value):
    spec: StringInput
    value: str

    def render(self, responses: Sequence[Any]) -> Any:
        return self.value

    def copy(self) -> StringValue:
        return StringValue(self.spec, self.value)

    def describe(self) -> Any:
        return self.value


@dataclass
class EnumValue(Value):
    """One of the documented values, by position in ``spec.values``."""

    spec: EnumInput
    index: int

    @property
    def value(self) -> Any:
        return self.spec.values[self.index]

    def render(self, responses: Sequence[Any]) -> Any:
        return self.value

    def copy(self) -> EnumValue:
        return EnumValue(self.spec, self.index)

    def describe(self) -> Any:
        return self.value


@dataclass
class NullValue(Value):
    """JSON ``null`` (documented for nullable specs; possible for any spec)."""

    spec: InputSpec

    def render(self, responses: Sequence[Any]) -> Any:
        return None

    def copy(self) -> NullValue:
        return NullValue(self.spec)

    def describe(self) -> Any:
        return None


@dataclass
class OptionalValue(Value):
    """A position that need not be sent: ``present`` decides whether ``inner`` is."""

    inner: Value
    present: bool

    @property
    def spec(self) -> InputSpec:  # type: ignore[override]
        return self.inner.spec

    def render(self, responses: Sequence[Any]) -> Any:
        return self.inner.render(responses) if self.present else ABSENT

    def copy(self) -> OptionalValue:
        return OptionalValue(self.inner.copy(), self.present)

    def describe(self) -> Any:
        return self.inner.describe() if self.present else ABSENT

    def children(self) -> tuple[Value, ...]:
        return (self.inner,)


@dataclass
class ObjectValue(Value):
    """A JSON object; absent optional fields are left out when rendered."""

    spec: ObjectInput
    fields: dict[str, Value] = field(default_factory=dict)

    def render(self, responses: Sequence[Any]) -> Any:
        rendered = {name: value.render(responses) for name, value in self.fields.items()}
        return {name: value for name, value in rendered.items() if value is not ABSENT}

    def copy(self) -> ObjectValue:
        return ObjectValue(self.spec, {name: v.copy() for name, v in self.fields.items()})

    def describe(self) -> Any:
        described = {name: value.describe() for name, value in self.fields.items()}
        return {name: value for name, value in described.items() if value is not ABSENT}

    def children(self) -> tuple[Value, ...]:
        return tuple(self.fields.values())


@dataclass
class ArrayValue(Value):
    spec: ArrayInput
    items: list[Value] = field(default_factory=list)

    def render(self, responses: Sequence[Any]) -> Any:
        rendered = (item.render(responses) for item in self.items)
        return [value for value in rendered if value is not ABSENT]

    def copy(self) -> ArrayValue:
        return ArrayValue(self.spec, [item.copy() for item in self.items])

    def describe(self) -> Any:
        return [item.describe() for item in self.items]

    def children(self) -> tuple[Value, ...]:
        return tuple(self.items)


@dataclass
class ChoiceValue(Value):
    """``oneOf`` / ``anyOf``: the alternative at ``index`` with its value."""

    spec: ChoiceInput
    index: int
    option: Value

    def render(self, responses: Sequence[Any]) -> Any:
        return self.option.render(responses)

    def copy(self) -> ChoiceValue:
        return ChoiceValue(self.spec, self.index, self.option.copy())

    def describe(self) -> Any:
        return self.option.describe()

    def children(self) -> tuple[Value, ...]:
        return (self.option,)


@dataclass
class ResponseRef(Value):
    """The value at ``path`` in the response body of earlier action ``action`` (0-based).

    ``path`` is a small JSONPath subset: ``$`` (the whole body), ``$.id``,
    ``$.items[0].id``.
    """

    spec: InputSpec
    action: int
    path: str

    def __post_init__(self) -> None:
        _parse_path(self.path)  # reject a malformed path at construction time

    def render(self, responses: Sequence[Any]) -> Any:
        if not 0 <= self.action < len(responses):
            raise UnresolvedReferenceError(
                f"action {self.action} has no response yet ({len(responses)} available)"
            )
        current = responses[self.action]
        for step in _parse_path(self.path):
            try:
                current = current[step]
            except (KeyError, IndexError, TypeError):
                raise UnresolvedReferenceError(
                    f"{self.path} not found in the response of action {self.action}"
                ) from None
        return current

    def copy(self) -> ResponseRef:
        return ResponseRef(self.spec, self.action, self.path)

    def describe(self) -> Any:
        return {"from_action": self.action, "path": self.path}


_PATH_STEP = re.compile(r"\.([A-Za-z_][\w-]*)|\[(\d+)\]")


def _parse_path(path: str) -> tuple[str | int, ...]:
    if not path.startswith("$"):
        raise ValueError(f"response path must start with '$': {path!r}")
    steps: list[str | int] = []
    position = 1
    while position < len(path):
        match = _PATH_STEP.match(path, position)
        if match is None:
            raise ValueError(f"unsupported response path {path!r} at offset {position}")
        name, index = match.groups()
        steps.append(name if name is not None else int(index))
        position = match.end()
    return tuple(steps)


def placeholder(spec: InputSpec) -> Value:
    """A structurally complete value for ``spec`` built from fixed, documented choices:
    the lower bound of a range, the first enum value, the shortest string, required
    properties present and optional ones absent.

    It is a starting point for constructing test cases by hand or by a method, not a
    generator: it is deterministic and makes no attempt to be valid beyond the bounds
    (a ``pattern`` or ``format`` is not satisfied).
    """
    if isinstance(spec, BooleanInput):
        return BooleanValue(spec, False)
    if isinstance(spec, IntegerInput):
        return IntegerValue(spec, _lowest_integer(spec))
    if isinstance(spec, NumberInput):
        low = spec.minimum if spec.minimum is not None else 0.0
        return NumberValue(spec, low)
    if isinstance(spec, StringInput):
        return StringValue(spec, "a" * (spec.min_length or 0))
    if isinstance(spec, EnumInput):
        return EnumValue(spec, 0) if spec.values else NullValue(spec)
    if isinstance(spec, ArrayInput):
        return ArrayValue(spec, [placeholder(spec.item) for _ in range(spec.min_items or 0)])
    if isinstance(spec, ObjectInput):
        fields: dict[str, Value] = {}
        for prop in spec.properties:
            inner = placeholder(prop.spec)
            fields[prop.name] = inner if prop.required else OptionalValue(inner, present=False)
        return ObjectValue(spec, fields)
    if isinstance(spec, ChoiceInput) and spec.options:
        return ChoiceValue(spec, 0, placeholder(spec.options[0]))
    if isinstance(spec, RecursiveInput | AnyInput | ChoiceInput):
        return NullValue(spec)
    raise TypeError(f"no value type for {type(spec).__name__}")


def _lowest_integer(spec: IntegerInput) -> int:
    low = 0 if spec.minimum is None else spec.minimum + (1 if spec.exclusive_minimum else 0)
    if spec.multiple_of:
        low = -(-low // spec.multiple_of) * spec.multiple_of  # round up to a multiple
    return low
