import math

import pytest

from restgen.errors import MeasurementError
from restgen.evaluation.statistics import (
    a12,
    bootstrap_median_ci,
    holm,
    iqr,
    mann_whitney,
    median,
    project_equal_mean,
    wilcoxon,
)


def test_a12_and_magnitude() -> None:
    assert a12([3, 4], [1, 2]) == 1.0
    assert a12([1, 2], [1, 2]) == 0.5
    comparison = mann_whitney([10, 11, 12, 13, 14], [1, 2, 3, 4, 5])
    assert comparison.a12 == 1.0
    assert comparison.magnitude == "large"
    assert comparison.p_value < 0.05


def test_identical_samples_have_no_difference() -> None:
    assert mann_whitney([1, 1, 1], [1, 1, 1]).p_value == 1.0
    assert wilcoxon([1, 2, 3], [1, 2, 3]).a12 == 0.5


def test_wilcoxon_paired() -> None:
    result = wilcoxon([0.9, 0.8, 0.7, 0.95, 0.85, 0.75], [0.5, 0.4, 0.3, 0.55, 0.45, 0.35])
    assert result.p_value < 0.05
    with pytest.raises(MeasurementError):
        wilcoxon([1, 2], [1])


def test_holm_is_monotone_and_capped() -> None:
    adjusted = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert math.isclose(adjusted["a"], 0.03)
    assert math.isclose(adjusted["c"], 0.06)
    assert math.isclose(adjusted["b"], 0.06)  # monotone: never below a smaller p's value
    assert holm({"x": 0.9, "y": 0.8})["x"] == 1.0


def test_descriptives_and_bootstrap() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 100.0]
    assert median(values) == 3.0
    assert iqr(values) == (2.0, 4.0)
    assert iqr([5.0]) == (5.0, 5.0)
    low, high = bootstrap_median_ci(values, resamples=2000, seed=1)
    assert low <= 3.0 <= high
    assert bootstrap_median_ci(values, resamples=2000, seed=1) == (low, high)


def test_project_equal_mean_weights_services_equally() -> None:
    assert project_equal_mean({"big": [0.2, 0.2, 0.2], "small": [1.0]}) == 0.6


@pytest.mark.parametrize("bad", [[], [float("nan")]])
def test_invalid_samples(bad: list[float]) -> None:
    with pytest.raises(MeasurementError):
        median(bad)
