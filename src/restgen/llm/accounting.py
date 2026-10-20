"""LLM usage accounting: every call, its tokens, latency and cost, as a paper reports them.

* Prices live in ``configs/pricing.toml``. Every entry must name its source URL and the
  date it was checked; a model without an entry has an *unknown* cost (``None``), never 0.
* Each call is appended to ``llm_usage.jsonl`` in the run directory with the price that
  was in force, so later price changes do not rewrite old results.
* ``purpose`` names the caller (e.g. ``scout.construct``, ``employed.neighbour``): costs and
  successes can then be attributed to the component that spent them (ablations).
* A run may set a USD budget; exceeding it raises :class:`BudgetExceededError`.
"""

from __future__ import annotations

import statistics
import threading
import time
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from restgen.errors import ConfigError, MeasurementError, RestgenError
from restgen.jsonio import append_jsonl, read_jsonl

USAGE_FILE = "llm_usage.jsonl"
PER_TOKENS = 1_000_000


class BudgetExceededError(RestgenError):
    """The run's LLM budget is spent; the method must stop calling the model."""


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M tokens, as published by the provider."""

    provider: str
    model: str
    input: float
    output: float
    cached_input: float | None  # None: the provider has no cache discount
    source: str  # URL of the price page
    checked_on: str  # ISO date the page was read

    def cost(self, input_tokens: int, cached_input_tokens: int, output_tokens: int) -> float:
        uncached = input_tokens - cached_input_tokens
        cached_rate = self.cached_input if self.cached_input is not None else self.input
        return (
            uncached * self.input + cached_input_tokens * cached_rate + output_tokens * self.output
        ) / PER_TOKENS


class PricingTable:
    def __init__(self, prices: Iterable[ModelPrice]) -> None:
        self._prices = {(p.provider, p.model): p for p in prices}

    @classmethod
    def load(cls, path: Path) -> PricingTable:
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(f"pricing table not found: {path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
        prices = []
        for index, entry in enumerate(raw.get("price", [])):
            where = f"{path.name} price[{index}]"
            try:
                price = ModelPrice(
                    provider=str(entry["provider"]),
                    model=str(entry["model"]),
                    input=float(entry["input"]),
                    output=float(entry["output"]),
                    cached_input=None
                    if entry.get("cached_input") is None
                    else float(entry["cached_input"]),
                    source=str(entry["source"]),
                    checked_on=str(entry["checked_on"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ConfigError(f"{where}: incomplete price entry ({exc})") from exc
            if not price.source.startswith(("http://", "https://")):
                raise ConfigError(f"{where}: source must be the URL of the price page")
            try:
                date.fromisoformat(price.checked_on)
            except ValueError as exc:
                raise ConfigError(f"{where}: checked_on must be an ISO date") from exc
            if min(price.input, price.output, price.cached_input or 0.0) < 0:
                raise ConfigError(f"{where}: prices must not be negative")
            prices.append(price)
        return cls(prices)

    def get(self, provider: str, model: str) -> ModelPrice | None:
        return self._prices.get((provider, model))


@dataclass(frozen=True)
class LlmCall:
    call_id: int
    started_at: float  # unix time
    duration_ms: float
    provider: str
    model: str
    purpose: str
    attempt: int  # 1 for the first try, >1 for retries of the same request
    status: str  # ok | error | truncated
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int  # hidden reasoning, already included in output_tokens if billed so
    temperature: float | None
    max_tokens: int | None
    seed: int | None
    request_sha256: str  # hash of the exact request: caching and replay evidence
    cost_usd: float | None  # None: model not in the pricing table
    price: Mapping[str, Any] | None  # the price entry used, frozen into the record

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


class UsageLedger:
    """Thread-safe, append-only ledger of the LLM calls of one run."""

    def __init__(self, path: Path, pricing: PricingTable, max_usd: float | None = None) -> None:
        self.path = path
        self._pricing = pricing
        self._max_usd = max_usd
        self._lock = threading.Lock()
        self._next_id = 1
        self._spent = 0.0
        if path.is_file():  # resuming: continue numbering and spending
            for record in read_jsonl(path):
                self._next_id = max(self._next_id, int(record["call_id"]) + 1)
                self._spent += float(record["cost_usd"] or 0.0)

    @property
    def spent_usd(self) -> float:
        with self._lock:
            return self._spent

    def check_budget(self) -> None:
        """Call before a request: refuses once the budget is spent."""
        if self._max_usd is not None and self.spent_usd >= self._max_usd:
            raise BudgetExceededError(f"LLM budget of {self._max_usd} USD is spent")

    def record(
        self,
        *,
        provider: str,
        model: str,
        purpose: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: float,
        request_sha256: str,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
        attempt: int = 1,
        status: str = "ok",
        temperature: float | None = None,
        max_tokens: int | None = None,
        seed: int | None = None,
        started_at: float | None = None,
    ) -> LlmCall:
        if min(input_tokens, output_tokens, cached_input_tokens, reasoning_tokens) < 0:
            raise MeasurementError("token counts must not be negative")
        if cached_input_tokens > input_tokens:
            raise MeasurementError("cached input tokens exceed input tokens")
        price = self._pricing.get(provider, model)
        cost = (
            price.cost(input_tokens, cached_input_tokens, output_tokens)
            if price is not None
            else None
        )
        with self._lock:
            call = LlmCall(
                call_id=self._next_id,
                started_at=started_at if started_at is not None else time.time(),
                duration_ms=round(duration_ms, 3),
                provider=provider,
                model=model,
                purpose=purpose,
                attempt=attempt,
                status=status,
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
                request_sha256=request_sha256,
                cost_usd=None if cost is None else round(cost, 8),
                price=None if price is None else asdict(price),
            )
            self._next_id += 1
            self._spent += cost or 0.0
            append_jsonl(self.path, call.to_record())
        return call


def usage_summary(path: Path) -> dict[str, Any] | None:
    """Totals for metrics.json; None when the run made no LLM calls."""
    if not path.is_file():
        return None
    calls = list(read_jsonl(path))
    if not calls:
        return None
    by: dict[str, dict[str, dict[str, float]]] = {"model": {}, "purpose": {}}
    for call in calls:
        for key, name in (
            ("model", f"{call['provider']}/{call['model']}"),
            ("purpose", str(call["purpose"])),
        ):
            bucket = by[key].setdefault(
                name, {"calls": 0.0, "input_tokens": 0.0, "output_tokens": 0.0, "usd": 0.0}
            )
            bucket["calls"] += 1
            bucket["input_tokens"] += call["input_tokens"]
            bucket["output_tokens"] += call["output_tokens"]
            bucket["usd"] += call["cost_usd"] or 0.0
    unpriced = sum(1 for c in calls if c["cost_usd"] is None)
    total_cost = sum(c["cost_usd"] or 0.0 for c in calls)
    return {
        "llm_calls": len(calls),
        "llm_failed_calls": sum(1 for c in calls if c["status"] != "ok"),
        "llm_retries": sum(1 for c in calls if c["attempt"] > 1),
        "llm_input_tokens": sum(c["input_tokens"] for c in calls),
        "llm_cached_input_tokens": sum(c["cached_input_tokens"] for c in calls),
        "llm_output_tokens": sum(c["output_tokens"] for c in calls),
        "llm_reasoning_tokens": sum(c["reasoning_tokens"] for c in calls),
        # a single unpriced call makes the total unknown rather than silently too low
        "usd": None if unpriced else round(total_cost, 6),
        "unpriced_calls": unpriced,
        "latency_ms_median": statistics.median(c["duration_ms"] for c in calls),
        "llm_seconds_total": round(sum(c["duration_ms"] for c in calls) / 1000, 3),
        "models": sorted(by["model"]),
        "by_model": by["model"],
        "by_purpose": by["purpose"],
    }
