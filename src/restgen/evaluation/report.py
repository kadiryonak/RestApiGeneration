"""Compare groups of runs (tools / configurations) over repeated seeds.

Per service and metric: median [Q1, Q3] (n) per group; every group is compared with the
first (reference) group by Mann-Whitney U + Vargha-Delaney A12 over the independent
repetitions, with Holm correction over all comparisons of the same metric. Aggregates use
the project-equal mean of per-service medians, computed separately for real and
artificial services (artificial results are never mixed into the headline numbers).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from restgen.errors import RestgenError
from restgen.evaluation.measure import METRICS_FILE
from restgen.evaluation.statistics import holm, iqr, mann_whitney, median, project_equal_mean


@dataclass(frozen=True)
class Metric:
    name: str
    extract: Callable[[Mapping[str, Any]], float | None]
    higher_is_better: bool | None  # None: descriptive only (cost)


def _path(*keys: str) -> Callable[[Mapping[str, Any]], float | None]:
    def extract(metrics: Mapping[str, Any]) -> float | None:
        node: Any = metrics
        for key in keys:
            if not isinstance(node, Mapping) or node.get(key) is None:
                return None
            node = node[key]
        return float(node)

    return extract


METRICS = (
    Metric("operation_success_coverage", _path("operations", "operation_success_coverage"), True),
    Metric("operation_attempt_coverage", _path("operations", "operation_attempt_coverage"), True),
    Metric("line_coverage", _path("exploration_coverage", "line_coverage"), True),
    Metric("branch_coverage", _path("exploration_coverage", "branch_coverage"), True),
    Metric("unique_failures", _path("faults", "unique_failures"), True),
    Metric("unique_crash_locations", _path("faults", "unique_crash_locations"), True),
    Metric("output_line_coverage", _path("output_coverage", "line_coverage"), True),
    Metric("line_retention", _path("retention", "line_retention"), True),
    Metric("pass_rate", _path("suite", "pass_rate"), None),
    Metric("http_calls", _path("cost", "http_calls"), None),
    Metric("wall_seconds", _path("cost", "wall_seconds"), None),
)

# group label -> service -> metric -> values (one per run)
Data = dict[str, dict[str, dict[str, list[float]]]]


def collect(results_dir: Path, groups: Mapping[str, Sequence[str]]) -> tuple[Data, dict[str, str]]:
    """``groups``: label -> run directory globs relative to ``results/runs`` (e.g.
    ``smoke/*/schemathesis/*``). Returns the data and service -> category."""
    data: Data = {}
    categories: dict[str, str] = {}
    for label, patterns in groups.items():
        per_service: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        files = sorted(
            {f for p in patterns for f in (results_dir / "runs").glob(f"{p}/{METRICS_FILE}")}
        )
        if not files:
            raise RestgenError(f"group {label!r}: no {METRICS_FILE} under {list(patterns)}")
        for file in files:
            metrics = json.loads(file.read_text(encoding="utf-8"))
            service = str(metrics["service"])
            categories[service] = str(metrics.get("category", "real"))
            for metric in METRICS:
                value = metric.extract(metrics)
                if value is not None:
                    per_service[service][metric.name].append(value)
        data[label] = {s: dict(m) for s, m in per_service.items()}
    return data, categories


def build_report(
    name: str, data: Data, categories: Mapping[str, str]
) -> tuple[str, dict[str, Any]]:
    labels = list(data)
    reference = labels[0]
    services = sorted({s for group in data.values() for s in group})
    comparisons: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)  # metric -> key -> cmp
    for metric in METRICS:
        raw: dict[str, Any] = {}
        for label in labels[1:]:
            for service in services:
                x = data[label].get(service, {}).get(metric.name, [])
                y = data[reference].get(service, {}).get(metric.name, [])
                if len(x) >= 2 and len(y) >= 2:
                    raw[f"{label}|{service}"] = mann_whitney(x, y)
        adjusted = holm({k: c.p_value for k, c in raw.items()}) if raw else {}
        for key, comparison in raw.items():
            comparisons[metric.name][key] = {
                "p_value": comparison.p_value,
                "p_holm": adjusted[key],
                "a12": comparison.a12,
                "magnitude": comparison.magnitude,
            }

    lines = [
        f"# {name}",
        "",
        f"Reference group: **{reference}**. "
        "Cells: median [Q1, Q3] (n runs). A12 > 0.5 means the group's values are larger "
        "than the reference's; p is Holm-corrected over all comparisons of that metric.",
        "",
    ]
    for service in services:
        lines += [
            f"## {service} ({categories.get(service, 'real')})",
            "",
            "| Metric | " + " | ".join(labels) + " |",
            "|---|" + "---|" * len(labels),
        ]
        for metric in METRICS:
            cells = []
            for label in labels:
                values = data[label].get(service, {}).get(metric.name, [])
                cell = _describe(values)
                key = f"{label}|{service}"
                if key in comparisons[metric.name]:
                    c = comparisons[metric.name][key]
                    cell += f"<br>A12={c['a12']:.2f} ({c['magnitude']}), p={c['p_holm']:.3g}"
                cells.append(cell)
            if any(cell != "-" for cell in cells):
                lines.append(f"| {metric.name} | " + " | ".join(cells) + " |")
        lines.append("")

    aggregates: dict[str, dict[str, dict[str, float]]] = {}
    for category in ("real", "artificial"):
        members = [s for s in services if categories.get(s, "real") == category]
        if not members:
            continue
        lines += [
            f"## Project-equal mean of per-service medians ({category}, {len(members)} service(s))",
            "",
            "| Metric | " + " | ".join(labels) + " |",
            "|---|" + "---|" * len(labels),
        ]
        aggregates[category] = {}
        for metric in METRICS:
            row = {}
            for label in labels:
                per = {
                    s: data[label][s][metric.name]
                    for s in members
                    if data[label].get(s, {}).get(metric.name)
                }
                if len(per) == len(members):  # only when every service has the metric
                    row[label] = project_equal_mean(per)
            if row:
                aggregates[category][metric.name] = row
                lines.append(
                    f"| {metric.name} | "
                    + " | ".join(f"{row[label]:.4g}" if label in row else "-" for label in labels)
                    + " |"
                )
        lines.append("")

    payload = {
        "name": name,
        "reference": reference,
        "groups": labels,
        "data": data,
        "comparisons": comparisons,
        "aggregates": aggregates,
    }
    return "\n".join(lines), payload


def _describe(values: Sequence[float]) -> str:
    if not values:
        return "-"
    q1, q3 = iqr(values)
    return f"{median(values):.4g} [{q1:.4g}, {q3:.4g}] ({len(values)})"
