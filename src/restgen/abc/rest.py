"""Resource-aware construction and mutation of structured REST test cases."""

from __future__ import annotations

import random
import string

from restgen.abc.archive import TargetArchive
from restgen.abc.dependencies import DependencyGraph, resource_name
from restgen.core.representation.action import HttpAction
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
from restgen.core.representation.templates import Location, OperationTemplate
from restgen.core.representation.testcase import TestCase
from restgen.core.representation.values import (
    ArrayValue,
    BooleanValue,
    ChoiceValue,
    EnumValue,
    IntegerValue,
    NullValue,
    NumberValue,
    ObjectValue,
    OptionalValue,
    ResponseRef,
    StringValue,
    Value,
)


class RestTestOperator:
    """DABC-HS operator with lifecycle construction and resource-group mutations."""

    def __init__(
        self,
        templates: tuple[OperationTemplate, ...],
        graph: DependencyGraph,
        smart_sampling_rate: float,
        mutation_rate: float,
        max_actions: int,
    ) -> None:
        if not templates:
            raise ValueError("at least one operation template is required")
        self.templates = templates
        self.by_key = {template.key: template for template in templates}
        self.graph = graph
        self.smart_sampling_rate = smart_sampling_rate
        self.mutation_rate = mutation_rate
        self.max_actions = max_actions

    def sample(self, archive: TargetArchive[TestCase], rng: random.Random) -> TestCase:
        target = rng.choice(self.templates)
        if rng.random() <= self.smart_sampling_rate:
            return self.lifecycle(target.key, rng)
        length = rng.randint(1, min(3, self.max_actions))
        return TestCase([self._action(rng.choice(self.templates), rng) for _ in range(length)])

    def lifecycle(self, target: str, rng: random.Random) -> TestCase:
        actions: list[HttpAction] = []
        added: dict[str, int] = {}
        visiting: set[str] = set()

        def add(operation: str) -> None:
            if operation in visiting or len(actions) >= self.max_actions:
                return
            visiting.add(operation)
            for prerequisite in self.graph.prerequisites(operation):
                add(prerequisite)
            template = self.by_key[operation]
            action = self._action(template, rng)
            for prerequisite in self.graph.prerequisites(operation):
                source = added.get(prerequisite)
                if source is not None:
                    self._chain(action, prerequisite, operation, source)
            actions.append(action)
            added[operation] = len(actions) - 1
            visiting.remove(operation)

        add(target)
        case = TestCase(actions)
        case.validate()
        return case

    def mutate(
        self,
        candidate: TestCase,
        mutations: int,
        archive: TargetArchive[TestCase],
        rng: random.Random,
    ) -> TestCase:
        result = candidate.copy()
        for _ in range(mutations):
            if rng.random() > self.mutation_rate:
                continue
            choices = ["value", "add", "delete", "template", "reorder"]
            kind = rng.choice(choices)
            if kind == "add" and len(result) < self.max_actions:
                addition = self.lifecycle(rng.choice(self.templates).key, rng)
                room = self.max_actions - len(result)
                result.actions.extend(action.copy() for action in addition.actions[:room])
                self._repair_appended_references(result, len(result) - min(room, len(addition)))
            elif kind == "delete" and len(result) > 1:
                result.actions.pop()  # suffix deletion cannot leave a forward reference
            elif kind == "template":
                result = self.lifecycle(rng.choice(self.templates).key, rng)
            elif kind == "reorder":
                self._reorder_independent(result, rng)
            else:
                self._mutate_value(result, rng)
        result.validate()
        return result

    def _action(self, template: OperationTemplate, rng: random.Random) -> HttpAction:
        parameters: dict[str, Value] = {}
        body: Value | None = None
        for position in template.inputs:
            value = sample_value(position.spec, rng)
            if not position.required:
                value = OptionalValue(value, rng.random() < 0.5)
            if position.location is Location.BODY:
                body = value
            else:
                parameters[position.key] = value
        return HttpAction(template, parameters, body)

    def _chain(
        self, action: HttpAction, prerequisite: str, dependent: str, source_index: int
    ) -> None:
        evidence = self.graph.evidence(prerequisite, dependent)
        names = {item.input_name for item in evidence if item.input_name is not None}
        for position in action.operation.inputs:
            if position.name not in names:
                continue
            reference = ResponseRef(position.spec, source_index, "$.id")
            if position.location is Location.BODY:
                _replace_object_field(action.body, position.name, reference)
            else:
                action.parameters[position.key] = reference
        if action.body is not None:
            for name in names:
                reference = ResponseRef(_field_spec(action.body, name), source_index, "$.id")
                _replace_object_field(action.body, name, reference)

    @staticmethod
    def _repair_appended_references(case: TestCase, start: int) -> None:
        for action in case.actions[start:]:
            for reference in action.references():
                reference.action += start

    @staticmethod
    def _reorder_independent(case: TestCase, rng: random.Random) -> None:
        if len(case) < 2:
            return
        index = rng.randrange(len(case) - 1)
        left, right = case.actions[index], case.actions[index + 1]
        if any(left.references()) or any(right.references()):
            return
        if resource_name(left.operation) != resource_name(right.operation):
            case.actions[index], case.actions[index + 1] = right, left

    @staticmethod
    def _mutate_value(case: TestCase, rng: random.Random) -> None:
        mutable = [
            value
            for action in case.actions
            for value in action.values()
            if isinstance(
                value,
                BooleanValue | IntegerValue | NumberValue | StringValue | EnumValue | OptionalValue,
            )
            and not isinstance(value, ResponseRef)
        ]
        if not mutable:
            return
        value = rng.choice(mutable)
        if isinstance(value, BooleanValue):
            value.value = not value.value
        elif isinstance(value, IntegerValue):
            value.value += rng.choice((-1, 1)) * (2 ** rng.randint(0, 4))
        elif isinstance(value, NumberValue):
            value.value += rng.gauss(0.0, 1.0)
        elif isinstance(value, StringValue):
            value.value += rng.choice(string.ascii_letters)
        elif isinstance(value, EnumValue) and value.spec.values:
            value.index = rng.randrange(len(value.spec.values))
        elif isinstance(value, OptionalValue):
            value.present = not value.present


def sample_value(spec: InputSpec, rng: random.Random) -> Value:
    if spec.nullable and rng.random() < 0.05:
        return NullValue(spec)
    if isinstance(spec, BooleanInput):
        return BooleanValue(spec, bool(rng.getrandbits(1)))
    if isinstance(spec, IntegerInput):
        low = spec.minimum if spec.minimum is not None else -100
        high = spec.maximum if spec.maximum is not None else 100
        low += int(spec.exclusive_minimum)
        high -= int(spec.exclusive_maximum)
        return IntegerValue(spec, rng.randint(low, max(low, high)))
    if isinstance(spec, NumberInput):
        number_low = spec.minimum if spec.minimum is not None else -100.0
        number_high = spec.maximum if spec.maximum is not None else 100.0
        return NumberValue(spec, rng.uniform(number_low, max(number_low, number_high)))
    if isinstance(spec, StringInput):
        return StringValue(spec, _sample_string(spec, rng))
    if isinstance(spec, EnumInput):
        return EnumValue(spec, rng.randrange(len(spec.values))) if spec.values else NullValue(spec)
    if isinstance(spec, ArrayInput):
        low = spec.min_items or 0
        high = min(spec.max_items or max(low, 3), 3)
        items = [sample_value(spec.item, rng) for _ in range(rng.randint(low, high))]
        return ArrayValue(spec, items)
    if isinstance(spec, ObjectInput):
        fields: dict[str, Value] = {}
        for prop in spec.properties:
            value = sample_value(prop.spec, rng)
            fields[prop.name] = value if prop.required else OptionalValue(value, rng.random() < 0.5)
        return ObjectValue(spec, fields)
    if isinstance(spec, ChoiceInput) and spec.options:
        index = rng.randrange(len(spec.options))
        return ChoiceValue(spec, index, sample_value(spec.options[index], rng))
    if isinstance(spec, RecursiveInput | AnyInput | ChoiceInput):
        return NullValue(spec)
    raise TypeError(f"unsupported input specification: {type(spec).__name__}")


def _sample_string(spec: StringInput, rng: random.Random) -> str:
    semantic = {
        "email": "user@example.com",
        "date": "2026-10-29",
        "date-time": "2026-10-29T12:00:00Z",
        "uuid": "00000000-0000-4000-8000-000000000000",
        "uri": "https://example.com",
    }
    if spec.format in semantic:
        return semantic[spec.format]
    low = max(1, spec.min_length or 1)
    high = min(spec.max_length or max(low, 12), 12)
    return "".join(rng.choice(string.ascii_letters) for _ in range(rng.randint(low, high)))


def _replace_object_field(value: Value | None, name: str, replacement: Value) -> bool:
    if isinstance(value, OptionalValue):
        return _replace_object_field(value.inner, name, replacement)
    if isinstance(value, ObjectValue) and name in value.fields:
        value.fields[name] = replacement
        return True
    if isinstance(value, ObjectValue):
        return any(
            _replace_object_field(child, name, replacement) for child in value.fields.values()
        )
    return False


def _field_spec(value: Value, name: str) -> InputSpec:
    current = value.inner if isinstance(value, OptionalValue) else value
    if isinstance(current, ObjectValue) and name in current.fields:
        return current.fields[name].spec
    if isinstance(current, ObjectValue):
        for child in current.fields.values():
            try:
                return _field_spec(child, name)
            except KeyError:
                pass
    raise KeyError(name)
