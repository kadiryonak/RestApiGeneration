"""Search-domain types for the DABC-HS implementation.

Scores follow the paper's convention: zero means that a target was not reached,
values in ``(0, 1)`` are approach levels normalized from a branch distance, and one
means covered. Keeping per-target scores is essential; summing them would turn the
many-objective problem back into the basic ABC's single objective.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Generic, TypeVar

C = TypeVar("C")


@dataclass(frozen=True)
class TargetScore:
    target: str
    score: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"target score must lie within 0..1: {self.score}")

    @property
    def covered(self) -> bool:
        return self.score == 1.0


@dataclass(frozen=True)
class Fitness:
    targets: tuple[TargetScore, ...]
    server_errors: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        names = [item.target for item in self.targets]
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("fitness targets must be uniquely named and sorted")

    @classmethod
    def from_scores(
        cls, scores: dict[str, float], server_errors: frozenset[str] = frozenset()
    ) -> Fitness:
        return cls(tuple(TargetScore(name, scores[name]) for name in sorted(scores)), server_errors)

    def score(self, target: str) -> float:
        return next((item.score for item in self.targets if item.target == target), 0.0)

    @property
    def covered(self) -> frozenset[str]:
        return frozenset(item.target for item in self.targets if item.covered)

    @property
    def total_score(self) -> float:
        return sum(item.score for item in self.targets)


@dataclass(frozen=True)
class Individual(Generic[C]):
    candidate: C
    fitness: Fitness
    size: int
    trials: int = 0

    def failed(self) -> Individual[C]:
        return replace(self, trials=self.trials + 1)


def dominates(left: Individual[C], right: Individual[C], targets: frozenset[str]) -> bool:
    """Strict Pareto dominance on the currently uncovered targets."""
    if not targets:
        return (len(left.fitness.server_errors), -left.size) > (
            len(right.fitness.server_errors),
            -right.size,
        )
    better = False
    for target in targets:
        left_score, right_score = left.fitness.score(target), right.fitness.score(target)
        if left_score < right_score:
            return False
        better |= left_score > right_score
    return better


def better(left: Individual[C], right: Individual[C]) -> bool:
    """Parent/offspring decision without collapsing the archive objectives."""
    targets = frozenset(item.target for item in (*left.fitness.targets, *right.fitness.targets))
    if dominates(left, right, targets):
        return True
    if dominates(right, left, targets):
        return False
    return (
        len(left.fitness.covered),
        len(left.fitness.server_errors),
        left.fitness.total_score,
        -left.size,
    ) > (
        len(right.fitness.covered),
        len(right.fitness.server_errors),
        right.fitness.total_score,
        -right.size,
    )
