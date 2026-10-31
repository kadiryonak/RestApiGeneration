"""Discrete Dynamic Artificial Bee Colony with Hyper-Scout (DABC-HS).

This is deliberately candidate-agnostic. REST-specific construction and mutation are
operators; the search mechanics remain testable without a running service.
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from restgen.abc.archive import TargetArchive
from restgen.abc.models import Fitness, Individual, better
from restgen.abc.selection import preference_sort

C = TypeVar("C")


class SearchOperator(Protocol[C]):
    def sample(self, archive: TargetArchive[C], rng: random.Random) -> C: ...

    def mutate(
        self, candidate: C, mutations: int, archive: TargetArchive[C], rng: random.Random
    ) -> C: ...


@dataclass(frozen=True)
class DabcHsConfig:
    population_size: int
    limit: int
    archive_size: int
    mutation_threshold: int
    min_mutations: int
    max_mutations: int
    size_factors: tuple[float, ...]
    change_number: int
    reset_number: int
    max_evaluations: int
    max_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.population_size <= 0 or self.max_evaluations <= 0:
            raise ValueError("population size and evaluation budget must be positive")
        if not self.size_factors:
            raise ValueError("at least one size factor is required")
        if self.max_seconds is not None and self.max_seconds <= 0:
            raise ValueError("time budget must be positive")


@dataclass(frozen=True)
class SearchResult(Generic[C]):
    archive: TargetArchive[C]
    population: tuple[Individual[C], ...]
    evaluations: int
    cycles: int
    hyper_scout_resets: int
    size_factor_changes: int


class DabcHs(Generic[C]):
    def __init__(
        self,
        config: DabcHsConfig,
        operator: SearchOperator[C],
        evaluator: Callable[[C], Fitness],
        size_of: Callable[[C], int],
        seed: int,
    ) -> None:
        self.config = config
        self.operator = operator
        self.evaluator = evaluator
        self.size_of = size_of
        self.rng = random.Random(seed)
        self.archive: TargetArchive[C] = TargetArchive(config.archive_size)
        self.evaluations = 0
        self.deadline = (
            None if config.max_seconds is None else time.monotonic() + config.max_seconds
        )

    def run(self) -> SearchResult[C]:
        factor_index = no_improvement = cycles = resets = changes = 0
        population: list[Individual[C]] = []
        while self.evaluations < self.config.max_evaluations:
            employed_count = self._employed_count(factor_index)
            population = self._fill(population, employed_count)
            if not population:
                break
            improved = False
            employed_pool: list[Individual[C]] = []
            for parent in population[:employed_count]:
                if self._exhausted:
                    employed_pool.append(parent)
                    continue
                child = self._evaluate(
                    self.operator.mutate(
                        parent.candidate, self._mutation_count(), self.archive, self.rng
                    )
                )
                archive_improved = self.archive.add(child)
                if better(child, parent):
                    employed_pool.append(child)
                    improved = True
                else:
                    employed_pool.append(parent.failed())
                improved |= archive_improved
            pool = [*employed_pool, *population[employed_count:]]
            onlookers = self.config.population_size - employed_count
            for _ in range(onlookers):
                if self._exhausted:
                    break
                sampled_parent = self.archive.sample(self.rng)
                base = (
                    sampled_parent.candidate
                    if sampled_parent is not None
                    else self.operator.sample(self.archive, self.rng)
                )
                child = self._evaluate(
                    self.operator.mutate(base, self._mutation_count(), self.archive, self.rng)
                )
                archive_improved = self.archive.add(child)
                if sampled_parent is None or better(child, sampled_parent):
                    pool.append(child)
                    improved = True
                improved |= archive_improved
            population = preference_sort(pool, self.config.population_size, self.archive.covered)
            for index, individual in enumerate(population):
                if individual.trials > self.config.limit and not self._exhausted:
                    replacement = self._evaluate(self.operator.sample(self.archive, self.rng))
                    population[index] = replacement
                    improved |= self.archive.add(replacement)
            cycles += 1
            if improved:
                no_improvement = 0
            else:
                no_improvement += 1
                if no_improvement > self.config.change_number:
                    factor_index = (factor_index + 1) % len(self.config.size_factors)
                    changes += 1
                if no_improvement > self.config.reset_number:
                    population = []
                    no_improvement = 0
                    resets += 1
        return SearchResult(
            self.archive,
            tuple(population),
            self.evaluations,
            cycles,
            resets,
            changes,
        )

    @property
    def _exhausted(self) -> bool:
        time_exhausted = self.deadline is not None and time.monotonic() >= self.deadline
        return self.evaluations >= self.config.max_evaluations or time_exhausted

    def _evaluate(self, candidate: C) -> Individual[C]:
        if self._exhausted:
            raise RuntimeError("fitness evaluation budget exhausted")
        fitness = self.evaluator(candidate)
        self.evaluations += 1
        return Individual(candidate, fitness, self.size_of(candidate))

    def _fill(self, population: list[Individual[C]], count: int) -> list[Individual[C]]:
        kept = list(population)
        while len(kept) < count and not self._exhausted:
            individual = self._evaluate(self.operator.sample(self.archive, self.rng))
            kept.append(individual)
            self.archive.add(individual)
        return kept

    def _employed_count(self, factor_index: int) -> int:
        employed = self.config.population_size * self.config.size_factors[factor_index]
        return max(1, math.floor(employed))

    def _mutation_count(self) -> int:
        used = self.evaluations
        if used >= self.config.mutation_threshold:
            return self.config.max_mutations
        span = self.config.max_mutations - self.config.min_mutations
        return self.config.min_mutations + math.floor(span * used / self.config.mutation_threshold)
