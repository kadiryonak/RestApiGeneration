"""Target-based archive and feedback-directed selection for DABC-HS."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Generic, TypeVar

from restgen.abc.models import Individual

C = TypeVar("C")


@dataclass
class _TargetPopulation(Generic[C]):
    individuals: list[Individual[C]]
    selections: int = 0


class TargetArchive(Generic[C]):
    """At most ``capacity`` tests per target; covered targets retain one short test."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("archive capacity must be positive")
        self.capacity = capacity
        self._targets: dict[str, _TargetPopulation[C]] = {}

    @property
    def targets(self) -> frozenset[str]:
        return frozenset(self._targets)

    @property
    def covered(self) -> frozenset[str]:
        return frozenset(
            target
            for target, population in self._targets.items()
            if population.individuals[0].fitness.score(target) == 1.0
        )

    def population(self, target: str) -> tuple[Individual[C], ...]:
        found = self._targets.get(target)
        return () if found is None else tuple(found.individuals)

    def add(self, individual: Individual[C]) -> bool:
        improved = False
        for score in individual.fitness.targets:
            if score.score <= 0.0:
                continue
            population = self._targets.setdefault(score.target, _TargetPopulation([]))
            old_best = (
                self._best_key(population.individuals[0], score.target)
                if population.individuals
                else None
            )
            already_covered = (
                population.individuals
                and population.individuals[0].fitness.score(score.target) == 1.0
            )
            if already_covered:
                candidates = [*population.individuals, individual]
                covered = [item for item in candidates if item.fitness.score(score.target) == 1.0]
                population.individuals = [min(covered, key=lambda item: item.size)]
            else:
                population.individuals.append(individual)
                population.individuals.sort(
                    key=lambda item: self._best_key(item, score.target), reverse=True
                )
                del population.individuals[self.capacity :]
                if population.individuals[0].fitness.score(score.target) == 1.0:
                    population.individuals = [population.individuals[0]]
            new_best = self._best_key(population.individuals[0], score.target)
            if old_best is None or new_best > old_best:
                population.selections = 0
                improved = True
        return improved

    def sample(self, rng: random.Random) -> Individual[C] | None:
        available = [
            (target, population)
            for target, population in self._targets.items()
            if target not in self.covered and population.individuals
        ]
        if not available:
            return None
        minimum = min(population.selections for _, population in available)
        choices = [(target, pop) for target, pop in available if pop.selections == minimum]
        _, population = rng.choice(choices)
        population.selections += 1
        return rng.choice(population.individuals)

    @staticmethod
    def _best_key(individual: Individual[C], target: str) -> tuple[float, int]:
        return individual.fitness.score(target), -individual.size
