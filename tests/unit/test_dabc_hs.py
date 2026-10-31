import random
from dataclasses import replace

from restgen.abc.archive import TargetArchive
from restgen.abc.engine import DabcHs, DabcHsConfig
from restgen.abc.models import Fitness, Individual
from restgen.abc.selection import preference_sort


class IntegerOperator:
    def sample(self, archive: TargetArchive[int], rng: random.Random) -> int:
        return rng.randrange(10)

    def mutate(
        self, candidate: int, mutations: int, archive: TargetArchive[int], rng: random.Random
    ) -> int:
        return min(9, candidate + mutations)


def _fitness(value: int) -> Fitness:
    return Fitness.from_scores({"nine": 1.0 if value == 9 else 1.0 / (10 - value)})


def test_target_archive_shrinks_covered_target_and_prefers_short_test() -> None:
    archive: TargetArchive[str] = TargetArchive(3)
    archive.add(Individual("long", Fitness.from_scores({"branch": 1.0}), 5))
    archive.add(Individual("short", Fitness.from_scores({"branch": 1.0}), 2))
    archive.add(Individual("near", Fitness.from_scores({"branch": 0.9}), 1))

    assert [item.candidate for item in archive.population("branch")] == ["short"]
    assert archive.covered == {"branch"}


def test_feedback_directed_archive_samples_lowest_counter_target() -> None:
    archive: TargetArchive[str] = TargetArchive(2)
    archive.add(Individual("a", Fitness.from_scores({"a": 0.5}), 1))
    archive.add(Individual("b", Fitness.from_scores({"b": 0.5}), 1))
    rng = random.Random(3)

    first = archive.sample(rng)
    second = archive.sample(rng)

    assert first is not None and second is not None
    assert {first.candidate, second.candidate} == {"a", "b"}


def test_preference_sort_keeps_specialist_for_each_uncovered_target() -> None:
    left = Individual("left", Fitness.from_scores({"a": 0.9, "b": 0.1}), 2)
    right = Individual("right", Fitness.from_scores({"a": 0.1, "b": 0.9}), 2)
    average = Individual("average", Fitness.from_scores({"a": 0.5, "b": 0.5}), 1)

    selected = preference_sort([left, right, average], 2, frozenset())

    assert {item.candidate for item in selected} == {"left", "right"}


def test_dabc_hs_reaches_target_with_exact_evaluation_budget() -> None:
    search = DabcHs(
        DabcHsConfig(4, 2, 3, 5, 1, 3, (0.5, 0.75), 2, 3, 20),
        IntegerOperator(),
        _fitness,
        lambda _: 1,
        seed=7,
    )

    result = search.run()

    assert result.evaluations == 20
    assert result.archive.covered == {"nine"}


def test_hyper_scout_changes_factor_and_refreshes_stagnant_population() -> None:
    class Stagnant(IntegerOperator):
        def sample(self, archive: TargetArchive[int], rng: random.Random) -> int:
            return 0

        def mutate(
            self,
            candidate: int,
            mutations: int,
            archive: TargetArchive[int],
            rng: random.Random,
        ) -> int:
            return candidate

    result = DabcHs(
        DabcHsConfig(2, 1, 2, 10, 1, 1, (0.5, 1.0), 0, 1, 12),
        Stagnant(),
        _fitness,
        lambda _: 1,
        seed=1,
    ).run()

    assert result.size_factor_changes > 0
    assert result.hyper_scout_resets > 0


def test_trial_counter_is_immutable_on_individual() -> None:
    original = Individual("x", Fitness.from_scores({"a": 0.2}), 1)
    failed = original.failed()
    assert original.trials == 0 and failed.trials == 1
    assert replace(failed, trials=0) == original
