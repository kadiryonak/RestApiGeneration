"""1. The idea: state a property that must hold for ALL inputs, let Hypothesis find inputs.

Example-based test:   assert my_sort([3, 1, 2]) == [1, 2, 3]      (you pick the input)
Property-based test:  for any list xs, my_sort(xs) == sorted(xs)    (Hypothesis picks)

Run:  example/.venv/bin/pytest example/hypothesis/test_01_basics.py -v
One test below FAILS on purpose: read the "Failing test case" Hypothesis prints.
"""

from itertools import pairwise

from hypothesis import given
from hypothesis import strategies as st


def my_sort(values: list[int]) -> list[int]:
    """A buggy sort: it silently drops duplicates."""
    return sorted(set(values))


def correct_sort(values: list[int]) -> list[int]:
    return sorted(values)


# `st.lists(st.integers())` is a *strategy*: a recipe for generating values.
# @given runs the test many times (100 by default) with generated lists.
@given(st.lists(st.integers()))
def test_correct_sort_matches_builtin(values: list[int]) -> None:
    assert correct_sort(values) == sorted(values)


@given(st.lists(st.integers()))
def test_buggy_sort_matches_builtin(values: list[int]) -> None:
    # FAILS on purpose. Hypothesis finds a list with a duplicate, then *shrinks* it to the
    # simplest list that still fails: [0, 0].
    assert my_sort(values) == sorted(values)


# Properties do not need the right answer, only rules that must always hold:
@given(st.lists(st.integers()))
def test_sort_properties(values: list[int]) -> None:
    result = correct_sort(values)
    assert len(result) == len(values)  # nothing lost or added
    assert all(a <= b for a, b in pairwise(result))  # ordered
    assert correct_sort(result) == result  # idempotent: sorting twice changes nothing
