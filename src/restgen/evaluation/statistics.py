"""Statistics for tool comparisons (analysis §7.4, Schemathesis benchmarking guide).

* Independent repetitions of two tools on one service: two-sided Mann-Whitney U and the
  Vargha-Delaney A12 effect size; medians are reported, not means.
* Two tools across services (one value per service, e.g. the per-service median): paired
  two-sided Wilcoxon signed-rank. Never mix the two data structures.
* Several comparisons per metric: Holm correction.
* Uncertainty: percentile bootstrap confidence interval of the median.
* Aggregates: the project-equal mean (mean of per-service medians), so a service with
  hundreds of operations does not drown the small ones.
"""

from __future__ import annotations

import math
import random
import statistics as stdstats
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from scipy import stats as scistats

from restgen.errors import MeasurementError


@dataclass(frozen=True)
class Comparison:
    p_value: float
    a12: float  # P(X > Y) + 0.5 P(X = Y): 0.5 = no difference

    @property
    def magnitude(self) -> str:
        """Vargha & Delaney (2000) thresholds on |A12 - 0.5|."""
        distance = abs(self.a12 - 0.5)
        if distance < 0.06:
            return "negligible"
        if distance < 0.14:
            return "small"
        if distance < 0.21:
            return "medium"
        return "large"


def median(values: Sequence[float]) -> float:
    _require(values, 1)
    return float(stdstats.median(values))


def iqr(values: Sequence[float]) -> tuple[float, float]:
    """(Q1, Q3) by the inclusive method; a single value gives (v, v)."""
    _require(values, 1)
    if len(values) == 1:
        return float(values[0]), float(values[0])
    q1, _, q3 = stdstats.quantiles(values, n=4, method="inclusive")
    return float(q1), float(q3)


def a12(x: Sequence[float], y: Sequence[float]) -> float:
    _require(x, 1)
    _require(y, 1)
    greater = sum(1 for a in x for b in y if a > b)
    equal = sum(1 for a in x for b in y if a == b)
    return (greater + 0.5 * equal) / (len(x) * len(y))


def mann_whitney(x: Sequence[float], y: Sequence[float]) -> Comparison:
    """Independent samples (repetitions of two tools on the same service)."""
    _require(x, 2)
    _require(y, 2)
    if len(set(x) | set(y)) == 1:  # all values identical: no evidence of a difference
        return Comparison(1.0, 0.5)
    result = scistats.mannwhitneyu(x, y, alternative="two-sided")
    return Comparison(float(result.pvalue), a12(x, y))


def wilcoxon(x: Sequence[float], y: Sequence[float]) -> Comparison:
    """Paired samples (same services, one value per service and tool)."""
    if len(x) != len(y):
        raise MeasurementError("paired samples must have the same length")
    _require(x, 2)
    if all(a == b for a, b in zip(x, y, strict=True)):
        return Comparison(1.0, 0.5)
    result = scistats.wilcoxon(x, y, alternative="two-sided", zero_method="wilcox")
    return Comparison(float(result.pvalue), a12(x, y))


def holm(p_values: Mapping[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values (monotone, capped at 1)."""
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * p))
        adjusted[name] = running
    return adjusted


def bootstrap_median_ci(
    values: Sequence[float], confidence: float = 0.95, resamples: int = 10_000, seed: int = 0
) -> tuple[float, float]:
    """Percentile bootstrap CI of the median; seeded, so reports are reproducible."""
    _require(values, 1)
    if not 0 < confidence < 1:
        raise MeasurementError("confidence must be in (0, 1)")
    rng = random.Random(seed)
    n = len(values)
    medians = sorted(stdstats.median(rng.choices(values, k=n)) for _ in range(resamples))
    tail = (1 - confidence) / 2
    low = medians[max(0, math.floor(tail * resamples))]
    high = medians[min(resamples - 1, math.ceil((1 - tail) * resamples) - 1)]
    return float(low), float(high)


def project_equal_mean(per_service: Mapping[str, Sequence[float]]) -> float:
    """Mean over services of each service's median."""
    if not per_service:
        raise MeasurementError("no services to aggregate")
    return stdstats.fmean(median(values) for values in per_service.values())


def _require(values: Sequence[float], minimum: int) -> None:
    if len(values) < minimum:
        raise MeasurementError(f"need at least {minimum} value(s), got {len(values)}")
    if any(isinstance(v, float) and math.isnan(v) for v in values):
        raise MeasurementError("NaN in sample; undefined metrics must be filtered first")
