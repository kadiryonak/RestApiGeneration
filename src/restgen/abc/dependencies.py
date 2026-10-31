"""Resource dependencies from OpenAPI, Python state access, and fitness feedback.

Edges point from a prerequisite operation to the operation that benefits from it. Static
evidence is deliberately a hypothesis: runtime evidence strengthens or contradicts it.
"""

from __future__ import annotations

from dataclasses import dataclass

from restgen.core.representation.inputs import ChoiceInput, InputSpec, ObjectInput
from restgen.core.representation.resources import resource_dependencies, segments
from restgen.core.representation.templates import OperationTemplate


@dataclass(frozen=True)
class DependencyEvidence:
    prerequisite: str
    dependent: str
    input_name: str | None
    source: str
    weight: float


class DependencyGraph:
    def __init__(self, templates: tuple[OperationTemplate, ...]) -> None:
        self.templates = {template.key: template for template in templates}
        self._evidence: dict[tuple[str, str], list[DependencyEvidence]] = {}
        self._add_openapi_evidence(templates)

    def add(self, evidence: DependencyEvidence) -> None:
        if evidence.prerequisite == evidence.dependent:
            return
        edge = (evidence.prerequisite, evidence.dependent)
        self._evidence.setdefault(edge, []).append(evidence)

    def prerequisites(self, operation: str) -> tuple[str, ...]:
        ranked = [
            (sum(item.weight for item in evidence), prerequisite)
            for (prerequisite, dependent), evidence in self._evidence.items()
            if dependent == operation
        ]
        return tuple(name for _, name in sorted(ranked, reverse=True))

    def evidence(self, prerequisite: str, dependent: str) -> tuple[DependencyEvidence, ...]:
        return tuple(self._evidence.get((prerequisite, dependent), ()))

    def learn_state_accesses(self, accesses: dict[str, set[str]]) -> None:
        operations = list(accesses)
        for dependent in operations:
            for prerequisite in operations:
                if not accesses[dependent].intersection(accesses[prerequisite]):
                    continue
                method = self.templates.get(prerequisite)
                if method is not None and method.method in {"POST", "PUT", "PATCH"}:
                    self.add(
                        DependencyEvidence(prerequisite, dependent, None, "python-state", 0.75)
                    )

    def learn_fitness(self, operations: tuple[str, ...], improved_targets: frozenset[str]) -> None:
        if not improved_targets:
            return
        for index, dependent in enumerate(operations):
            for prerequisite in operations[:index]:
                self.add(
                    DependencyEvidence(
                        prerequisite,
                        dependent,
                        None,
                        "fitness-feedback",
                        min(1.0, 0.1 * len(improved_targets)),
                    )
                )

    def _add_openapi_evidence(self, templates: tuple[OperationTemplate, ...]) -> None:
        for dependency in resource_dependencies(templates):
            for creator in dependency.creators:
                self.add(
                    DependencyEvidence(
                        creator, dependency.operation, dependency.parameter, "openapi-path", 1.0
                    )
                )
        creators = _creators_by_resource(templates)
        for template in templates:
            for input_name in _input_names(template):
                stem = _identifier_stem(input_name)
                for resource, creator in creators.items():
                    if stem == resource:
                        self.add(
                            DependencyEvidence(
                                creator, template.key, input_name, "openapi-name", 0.5
                            )
                        )


def resource_name(template: OperationTemplate) -> str:
    constants = [part for part in segments(template.path) if not part.startswith("{")]
    return constants[-1] if constants else "root"


def _creators_by_resource(templates: tuple[OperationTemplate, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for template in templates:
        if template.method not in {"POST", "PUT"}:
            continue
        name = _singular(resource_name(template))
        result.setdefault(name, template.key)
    return result


def _input_names(template: OperationTemplate) -> set[str]:
    names: set[str] = set()
    for position in template.inputs:
        names.add(position.name)
        names.update(_property_names(position.spec))
    return names


def _property_names(spec: InputSpec) -> set[str]:
    if isinstance(spec, ObjectInput):
        return {
            name for prop in spec.properties for name in ({prop.name} | _property_names(prop.spec))
        }
    if isinstance(spec, ChoiceInput):
        return {name for option in spec.options for name in _property_names(option)}
    return set()


def _identifier_stem(name: str) -> str:
    lowered = name.lower().replace("-", "_")
    for suffix in ("_id", "id"):
        if lowered.endswith(suffix):
            return _singular(lowered[: -len(suffix)].rstrip("_"))
    return ""


def _singular(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    return name[:-1] if name.endswith("s") else name
