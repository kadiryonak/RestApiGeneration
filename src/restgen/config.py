"""Typed settings loaded from ``configs/restgen.toml`` (the single source of truth)."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from restgen.errors import ConfigError

DEFAULT_CONFIG = Path("configs/restgen.toml")


@dataclass(frozen=True)
class PathSettings:
    benchmark_manifest: Path
    benchmark_dir: Path
    results_dir: Path


@dataclass(frozen=True)
class BudgetSettings:
    """Per tool run. Each tool maps these onto its own knobs (see baselines/)."""

    max_time_seconds: int
    max_examples: int
    request_timeout_seconds: float


@dataclass(frozen=True)
class RepetitionSettings:
    seeds: tuple[int, ...]


@dataclass(frozen=True)
class EvaluationSettings:
    # An operation counts as successfully covered when one response falls in this range.
    success_status_min: int
    success_status_max: int
    server_error_min: int
    # Clean re-executions of a produced test suite (output coverage + stability).
    rerun_count: int


@dataclass(frozen=True)
class ProxySettings:
    max_body_bytes: int
    redact_headers: tuple[str, ...]


@dataclass(frozen=True)
class SchemathesisSettings:
    executable: Path
    extra_args: tuple[str, ...]


@dataclass(frozen=True)
class HypothesisSettings:
    python: Path


@dataclass(frozen=True)
class EvoMasterSettings:
    jar: Path
    java: str  # executable name or path
    python: Path  # environment the generated Python tests run in
    extra_args: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    root: Path
    paths: PathSettings
    budget: BudgetSettings
    repetitions: RepetitionSettings
    evaluation: EvaluationSettings
    proxy: ProxySettings
    schemathesis: SchemathesisSettings
    hypothesis: HypothesisSettings
    evomaster: EvoMasterSettings

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            if isinstance(value, list | tuple):
                return [convert(item) for item in value]
            return value

        data: dict[str, Any] = convert(asdict(self))
        return data


def load_settings(
    root: Path, config: Path = DEFAULT_CONFIG, overrides: Sequence[str] = ()
) -> Settings:
    """Load ``config`` (relative to ``root``) and apply ``section.key=value`` overrides.

    Override values are parsed as TOML literals, e.g. ``budget.max_time_seconds=600``
    or ``tools.schemathesis.extra_args=["--no-shrink"]``.
    """
    path = config if config.is_absolute() else root / config
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    for override in overrides:
        _apply_override(raw, override)
    return _build(root.resolve(), raw)


def _apply_override(raw: dict[str, Any], override: str) -> None:
    key, sep, literal = override.partition("=")
    if not sep or not key.strip():
        raise ConfigError(f"override must look like section.key=value: {override!r}")
    try:
        value = tomllib.loads(f"value = {literal.strip()}")["value"]
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"override value is not a TOML literal: {override!r}") from exc
    *parents, leaf = key.strip().split(".")
    node = raw
    for part in parents:
        child = node.get(part)
        if not isinstance(child, dict):
            raise ConfigError(f"unknown configuration section in override: {key!r}")
        node = child
    if leaf not in node:
        raise ConfigError(f"unknown configuration key in override: {key!r}")
    node[leaf] = value


def _section(raw: Mapping[str, Any], *names: str) -> Mapping[str, Any]:
    node: Any = raw
    for name in names:
        node = node.get(name) if isinstance(node, Mapping) else None
        if not isinstance(node, Mapping):
            raise ConfigError(f"missing configuration section [{'.'.join(names)}]")
    section: Mapping[str, Any] = node
    return section


def _get(section: Mapping[str, Any], key: str, kind: type, where: str) -> Any:
    if key not in section:
        raise ConfigError(f"missing configuration key {where}.{key}")
    value = section[key]
    # bool is an int subclass; never accept it where a number is expected
    if kind in (int, float) and isinstance(value, bool):
        raise ConfigError(f"{where}.{key} must be {kind.__name__}, got bool")
    if kind is float and isinstance(value, int):
        return float(value)
    if not isinstance(value, kind):
        raise ConfigError(f"{where}.{key} must be {kind.__name__}, got {type(value).__name__}")
    return value


def _str_tuple(section: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    values = _get(section, key, list, where)
    if not all(isinstance(item, str) for item in values):
        raise ConfigError(f"{where}.{key} must be a list of strings")
    return tuple(values)


def _build(root: Path, raw: Mapping[str, Any]) -> Settings:
    paths = _section(raw, "paths")
    budget = _section(raw, "budget")
    repetitions = _section(raw, "repetitions")
    evaluation = _section(raw, "evaluation")
    proxy = _section(raw, "proxy")
    schemathesis = _section(raw, "tools", "schemathesis")
    hypothesis = _section(raw, "tools", "hypothesis")
    evomaster = _section(raw, "tools", "evomaster")

    seeds = _get(repetitions, "seeds", list, "repetitions")
    if not seeds or not all(isinstance(s, int) and not isinstance(s, bool) for s in seeds):
        raise ConfigError("repetitions.seeds must be a non-empty list of integers")

    settings = Settings(
        root=root,
        paths=PathSettings(
            benchmark_manifest=root / _get(paths, "benchmark_manifest", str, "paths"),
            benchmark_dir=root / _get(paths, "benchmark_dir", str, "paths"),
            results_dir=root / _get(paths, "results_dir", str, "paths"),
        ),
        budget=BudgetSettings(
            max_time_seconds=_get(budget, "max_time_seconds", int, "budget"),
            max_examples=_get(budget, "max_examples", int, "budget"),
            request_timeout_seconds=_get(budget, "request_timeout_seconds", float, "budget"),
        ),
        repetitions=RepetitionSettings(seeds=tuple(seeds)),
        evaluation=EvaluationSettings(
            success_status_min=_get(evaluation, "success_status_min", int, "evaluation"),
            success_status_max=_get(evaluation, "success_status_max", int, "evaluation"),
            server_error_min=_get(evaluation, "server_error_min", int, "evaluation"),
            rerun_count=_get(evaluation, "rerun_count", int, "evaluation"),
        ),
        proxy=ProxySettings(
            max_body_bytes=_get(proxy, "max_body_bytes", int, "proxy"),
            redact_headers=tuple(h.lower() for h in _str_tuple(proxy, "redact_headers", "proxy")),
        ),
        schemathesis=SchemathesisSettings(
            executable=root / _get(schemathesis, "executable", str, "tools.schemathesis"),
            extra_args=_str_tuple(schemathesis, "extra_args", "tools.schemathesis"),
        ),
        hypothesis=HypothesisSettings(
            python=root / _get(hypothesis, "python", str, "tools.hypothesis"),
        ),
        evomaster=EvoMasterSettings(
            jar=root / _get(evomaster, "jar", str, "tools.evomaster"),
            java=_get(evomaster, "java", str, "tools.evomaster"),
            python=root / _get(evomaster, "python", str, "tools.evomaster"),
            extra_args=_str_tuple(evomaster, "extra_args", "tools.evomaster"),
        ),
    )
    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    budget, evaluation = settings.budget, settings.evaluation
    if budget.max_time_seconds <= 0 or budget.max_examples <= 0:
        raise ConfigError("budget.max_time_seconds and budget.max_examples must be positive")
    if budget.request_timeout_seconds <= 0:
        raise ConfigError("budget.request_timeout_seconds must be positive")
    if not 100 <= evaluation.success_status_min <= evaluation.success_status_max <= 599:
        raise ConfigError("evaluation success status range must lie within 100..599")
    if not 100 <= evaluation.server_error_min <= 599:
        raise ConfigError("evaluation.server_error_min must lie within 100..599")
    if evaluation.rerun_count < 1:
        raise ConfigError("evaluation.rerun_count must be at least 1")
    if settings.proxy.max_body_bytes < 0:
        raise ConfigError("proxy.max_body_bytes must not be negative")
