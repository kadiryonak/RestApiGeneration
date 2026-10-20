"""Search trace: a timestamped event log of what a search method did.

Method-neutral: phase names, candidate ids and operator ("origin") names are free strings,
so the same trace serves the ABC method (phases ``init``/``employed``/``onlooker``/
``scout``, origins such as ``phi``, ``llm``, ``random``), an ablation or any other search.

Every event carries ``t``: seconds since the search started on a monotonic clock (immune
to wall-clock adjustments), plus ``wall`` (unix time) to align with proxy traffic and LLM
calls. Events go to ``search_trace.jsonl``; :func:`trace_summary` turns them into the
numbers a paper reports: time and evaluations per phase, which operator produced
improvements and new targets, and when targets were first reached.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from restgen.errors import MeasurementError
from restgen.jsonio import append_jsonl, read_jsonl

TRACE_FILE = "search_trace.jsonl"


class SearchTrace:
    """Append-only event writer for one search run."""

    def __init__(
        self,
        path: Path,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = path
        self._clock = clock
        self._wall = wall_clock
        self._start = clock()
        self._lock = threading.Lock()
        self._phase: str | None = None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        self._emit("start")

    @property
    def elapsed(self) -> float:
        return self._clock() - self._start

    def _emit(self, kind: str, **fields: Any) -> None:
        with self._lock:
            record = {
                "t": round(self.elapsed, 6),
                "wall": self._wall(),
                "kind": kind,
                "phase": self._phase,
                **fields,
            }
            append_jsonl(self.path, record)

    @contextmanager
    def phase(self, name: str, **fields: Any) -> Iterator[None]:
        """Time a phase (``with trace.phase("employed", cycle=3): ...``). Phases do not
        nest: the search is in one phase at a time."""
        if self._phase is not None:
            raise MeasurementError(f"phase {name!r} started inside phase {self._phase!r}")
        started = self.elapsed
        self._phase = name
        self._emit("phase_start", **fields)
        try:
            yield
        finally:
            self._emit("phase_end", duration=round(self.elapsed - started, 6), **fields)
            self._phase = None

    def evaluation(
        self,
        candidate: str,
        origin: str,
        operations: Sequence[str],
        http_calls: int,
        new_targets: Sequence[str] = (),
        fitness: float | None = None,
        duration: float | None = None,
        **fields: Any,
    ) -> None:
        """One candidate was executed against the service and scored."""
        self._emit(
            "evaluation",
            candidate=candidate,
            origin=origin,
            operations=list(operations),
            http_calls=http_calls,
            new_targets=list(new_targets),
            fitness=fitness,
            duration=duration,
            **fields,
        )

    def improvement(self, candidate: str, origin: str, before: float, after: float) -> None:
        """A candidate replaced a worse one (greedy selection succeeded)."""
        self._emit("improvement", candidate=candidate, origin=origin, before=before, after=after)

    def abandon(self, candidate: str, trials: int) -> None:
        """A candidate was given up after ``trials`` failed attempts (ABC scout)."""
        self._emit("abandon", candidate=candidate, trials=trials)

    def checkpoint(self, **budget: Any) -> None:
        """Budget snapshot, e.g. ``evaluations=120, http_calls=900, usd=0.12``."""
        self._emit("checkpoint", **budget)

    def note(self, message: str, **fields: Any) -> None:
        self._emit("note", message=message, **fields)

    def finish(self, **fields: Any) -> None:
        if self._phase is not None:
            raise MeasurementError(f"finish() inside phase {self._phase!r}")
        self._emit("finish", **fields)


def read_trace(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise MeasurementError(f"search trace not found: {path}")
    return list(read_jsonl(path))


def trace_summary(events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not events or events[0].get("kind") != "start":
        raise MeasurementError("a search trace must begin with a start event")
    phases: dict[str, dict[str, float]] = {}
    origins: dict[str, dict[str, float]] = {}
    first_reached: dict[str, float] = {}
    evaluations = http_calls = abandoned = 0
    for event in events:
        kind = event["kind"]
        if kind == "phase_end":
            bucket = phases.setdefault(
                event["phase"], {"count": 0, "seconds": 0.0, "evaluations": 0}
            )
            bucket["count"] += 1
            bucket["seconds"] = round(bucket["seconds"] + float(event["duration"]), 6)
        elif kind == "evaluation":
            evaluations += 1
            http_calls += int(event["http_calls"])
            if event["phase"] is not None:
                phases.setdefault(event["phase"], {"count": 0, "seconds": 0.0, "evaluations": 0})[
                    "evaluations"
                ] += 1
            stats = _origin(origins, event["origin"])
            stats["evaluations"] += 1
            stats["http_calls"] += int(event["http_calls"])
            stats["new_targets"] += len(event["new_targets"])
            for target in event["new_targets"]:
                first_reached.setdefault(target, float(event["t"]))
        elif kind == "improvement":
            _origin(origins, event["origin"])["improvements"] += 1
        elif kind == "abandon":
            abandoned += 1
    for stats in origins.values():
        stats["improvement_rate"] = (
            stats["improvements"] / stats["evaluations"] if stats["evaluations"] else 0.0
        )
    reached = sorted(first_reached.values())
    return {
        "search_seconds": float(events[-1]["t"]),
        "finished": events[-1]["kind"] == "finish",
        "evaluations": evaluations,
        "http_calls": http_calls,
        "abandoned": abandoned,
        "phases": phases,
        "origins": origins,
        "targets_reached": len(first_reached),
        "seconds_to_last_new_target": reached[-1] if reached else None,
        "target_discovery_curve": [[t, i + 1] for i, t in enumerate(reached)],
    }


def _origin(origins: dict[str, dict[str, float]], name: str) -> dict[str, float]:
    return origins.setdefault(
        name, {"evaluations": 0, "http_calls": 0, "new_targets": 0, "improvements": 0}
    )
