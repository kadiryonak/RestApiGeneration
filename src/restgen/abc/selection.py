"""MOSA-style preference sorting used by the DABC-HS parent+offspring pool."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from restgen.abc.models import Individual, dominates

C = TypeVar("C")


def preference_sort(
    candidates: Sequence[Individual[C]], population_size: int, covered: frozenset[str]
) -> list[Individual[C]]:
    if population_size <= 0:
        raise ValueError("population size must be positive")
    if len(candidates) <= population_size:
        return list(candidates)
    all_targets = frozenset(
        score.target for candidate in candidates for score in candidate.fitness.targets
    )
    uncovered = all_targets - covered
    preferred: list[Individual[C]] = []
    for target in sorted(uncovered):
        best = max(candidates, key=lambda item: (item.fitness.score(target), -item.size))
        if not _contains_identity(preferred, best):
            preferred.append(best)
    if len(preferred) >= population_size:
        return _crowding_select(preferred, population_size, uncovered)
    remaining = [item for item in candidates if not _contains_identity(preferred, item)]
    for front in _fronts(remaining, uncovered):
        slots = population_size - len(preferred)
        if len(front) <= slots:
            preferred.extend(front)
        else:
            preferred.extend(_crowding_select(front, slots, uncovered))
            break
    return preferred


def _fronts(candidates: list[Individual[C]], targets: frozenset[str]) -> list[list[Individual[C]]]:
    fronts: list[list[Individual[C]]] = []
    remaining = list(candidates)
    while remaining:
        front = [
            item
            for item in remaining
            if not any(other is not item and dominates(other, item, targets) for other in remaining)
        ]
        fronts.append(front)
        remaining = [item for item in remaining if not _contains_identity(front, item)]
    return fronts


def _crowding_select(
    front: Sequence[Individual[C]], count: int, targets: frozenset[str]
) -> list[Individual[C]]:
    if count >= len(front):
        return list(front)
    distances = {id(item): 0.0 for item in front}
    for target in targets:
        ordered = sorted(front, key=lambda item: item.fitness.score(target))
        low, high = ordered[0].fitness.score(target), ordered[-1].fitness.score(target)
        distances[id(ordered[0])] = distances[id(ordered[-1])] = float("inf")
        if high == low:
            continue
        for index in range(1, len(ordered) - 1):
            before = ordered[index - 1].fitness.score(target)
            after = ordered[index + 1].fitness.score(target)
            distances[id(ordered[index])] += (after - before) / (high - low)
    return sorted(front, key=lambda item: (distances[id(item)], -item.size), reverse=True)[:count]


def _contains_identity(items: Sequence[Individual[C]], wanted: Individual[C]) -> bool:
    return any(item is wanted for item in items)
