"""Cost and size of producing a test suite (analysis §5.8)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Cost:
    wall_seconds: float
    http_calls: int  # every call the tool made during generation (from the proxy)
    llm_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    usd: float | None = 0.0  # None: an LLM was used but its price is unknown
    repair_rounds: int = 0
    tests_in_output: int | None = None  # None: the tool produces no persistent suite

    def summary(self) -> dict[str, Any]:
        return asdict(self)
