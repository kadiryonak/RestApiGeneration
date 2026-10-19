"""Fault funnel (analysis §5.5).

    candidate calls          every response with status >= server_error_min
      → unique failures      deduplicated by (operation, status, normalised error text)
      → verified bugs        signatures a person labelled ``app_bug`` in triage.toml
      → root causes          distinct ``root_cause`` ids among the verified bugs

500 identical 500 responses are one failure, not 500 bugs. A finding caused by a wrong
assumption of the generator or by the environment is never counted as an application bug.

For Python services the server log is also parsed: each traceback is reduced to
(exception type, innermost frame inside the service source), the location-based
deduplication used by the Schemathesis ICSE 2022 study.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from restgen.errors import MeasurementError
from restgen.openapi import OpenApiSpec
from restgen.traffic.models import HttpInteraction

TRIAGE_FILE = "triage.toml"
_VOLATILE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # uuid
    r"|0x[0-9a-f]+|\b[0-9a-f]{16,}\b"  # addresses, hashes
    r"|\d+(?:\.\d+)?",  # numbers, timestamps
    re.IGNORECASE,
)
_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\S+)')
_EXCEPTION = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning)\b)")


class Verdict(StrEnum):
    UNREVIEWED = "unreviewed"
    APP_BUG = "app_bug"
    TOOL_ASSUMPTION = "tool_assumption"  # the generator's wrong expectation
    ENVIRONMENT = "environment"  # infrastructure, rate limit, unavailable dependency


@dataclass(frozen=True)
class Failure:
    signature: str
    operation: str  # "METHOD /template" or "UNMATCHED METHOD /path"
    status: int
    occurrences: int
    example_target: str
    example_body: str


@dataclass(frozen=True)
class FaultFunnel:
    candidate_calls: int
    unique_failures: tuple[Failure, ...]
    verdicts: Mapping[str, Verdict]
    root_causes: Mapping[str, str]  # signature -> root cause id (verified bugs only)
    crash_locations: Mapping[str, int]  # "ExcType @ file:line" -> occurrences in server log

    @property
    def verified_bugs(self) -> int:
        return sum(
            1 for f in self.unique_failures if self.verdicts.get(f.signature) is Verdict.APP_BUG
        )

    @property
    def unreviewed(self) -> int:
        return sum(
            1
            for f in self.unique_failures
            if self.verdicts.get(f.signature, Verdict.UNREVIEWED) is Verdict.UNREVIEWED
        )

    @property
    def distinct_root_causes(self) -> int:
        return len({self.root_causes[s] for s in self.root_causes})

    def summary(self) -> dict[str, Any]:
        complete = self.unreviewed == 0
        return {
            "candidate_calls": self.candidate_calls,
            "unique_failures": len(self.unique_failures),
            "unique_crash_locations": len(self.crash_locations),
            "triage_complete": complete,
            "unreviewed_failures": self.unreviewed,
            # verified counts are only meaningful once triage is complete
            "verified_bugs": self.verified_bugs if complete else None,
            "distinct_root_causes": self.distinct_root_causes if complete else None,
            "verdicts": dict(Counter(v.value for v in self.verdicts.values())),
            "failures": [
                {
                    "signature": f.signature,
                    "operation": f.operation,
                    "status": f.status,
                    "occurrences": f.occurrences,
                    "verdict": self.verdicts.get(f.signature, Verdict.UNREVIEWED).value,
                }
                for f in self.unique_failures
            ],
        }


def normalise_error(text: str, limit: int = 300) -> str:
    return " ".join(_VOLATILE.sub("#", text[:limit]).split())


def failure_signature(operation: str, status: int, body: str) -> str:
    digest = hashlib.sha256(f"{operation}|{status}|{normalise_error(body)}".encode()).hexdigest()
    return digest[:16]


def unique_failures(
    spec: OpenApiSpec, interactions: Iterable[HttpInteraction], server_error_min: int
) -> tuple[int, tuple[Failure, ...]]:
    """Returns (candidate call count, deduplicated failures in first-seen order)."""
    candidates = 0
    seen: dict[str, Failure] = {}
    for interaction in interactions:
        if interaction.status is None or interaction.status < server_error_min:
            continue
        candidates += 1
        matched = spec.match(interaction.method, interaction.target)
        operation = (
            matched.operation.key
            if matched.operation
            else f"UNMATCHED {interaction.method} {matched.path}"
        )
        signature = failure_signature(operation, interaction.status, interaction.response_body)
        if signature in seen:
            previous = seen[signature]
            seen[signature] = Failure(
                signature,
                previous.operation,
                previous.status,
                previous.occurrences + 1,
                previous.example_target,
                previous.example_body,
            )
        else:
            seen[signature] = Failure(
                signature,
                operation,
                interaction.status,
                1,
                interaction.target,
                interaction.response_body[:500],
            )
    return candidates, tuple(seen.values())


def crash_locations(log: str, source_root: Path) -> dict[str, int]:
    """Python tracebacks in a server log → {"ExcType @ relative/file.py:line": count}.

    The location is the innermost frame inside ``source_root`` (the service's own code),
    so the same bug reached through different framework call paths is counted once."""
    root = str(source_root.resolve())
    found: Counter[str] = Counter()
    frame: tuple[str, str] | None = None
    in_traceback = False
    for line in log.splitlines():
        if line.startswith("Traceback (most recent call last)"):
            in_traceback, frame = True, None
            continue
        if not in_traceback:
            continue
        match = _FRAME.match(line)
        if match:
            path = match["file"]
            if path.startswith(root) and "site-packages" not in path:
                frame = (path[len(root) :].lstrip("/"), match["line"])
            continue
        exception = _EXCEPTION.match(line)
        if exception:
            # chained exceptions repeat the block; the last one wins for that traceback
            location = f"{frame[0]}:{frame[1]}" if frame else "<outside service code>"
            found[f"{exception['type']} @ {location}"] += 1
            in_traceback = False
    return dict(found)


def load_triage(path: Path) -> tuple[dict[str, Verdict], dict[str, str]]:
    """``triage.toml``: ``[failure.<signature>] verdict = "...", root_cause = "..."``."""
    if not path.is_file():
        return {}, {}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise MeasurementError(f"invalid triage file {path}: {exc}") from exc
    verdicts: dict[str, Verdict] = {}
    causes: dict[str, str] = {}
    for signature, entry in raw.get("failure", {}).items():
        try:
            verdict = Verdict(entry.get("verdict", Verdict.UNREVIEWED.value))
        except ValueError as exc:
            raise MeasurementError(f"{path}: unknown verdict for {signature}") from exc
        verdicts[signature] = verdict
        cause = str(entry.get("root_cause", "")).strip()
        if verdict is Verdict.APP_BUG:
            if not cause:
                raise MeasurementError(f"{path}: app_bug {signature} needs a root_cause id")
            causes[signature] = cause
    return verdicts, causes


def write_triage_template(path: Path, failures: Iterable[Failure]) -> None:
    """Append an ``unreviewed`` entry for every failure not yet in the triage file."""
    verdicts, _ = load_triage(path)
    lines = []
    for failure in failures:
        if failure.signature in verdicts:
            continue
        example = failure.example_body.replace('"""', "'''")[:300]
        lines += [
            f"[failure.{failure.signature}]",
            f"# {failure.operation} -> {failure.status} ({failure.occurrences}x), e.g. "
            f"{failure.example_target}",
            f'example = """{example}"""',
            'verdict = "unreviewed"  # app_bug | tool_assumption | environment',
            'root_cause = ""  # required for app_bug: same id = same underlying defect',
            "",
        ]
    if lines:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def fault_funnel(
    spec: OpenApiSpec,
    interactions: Iterable[HttpInteraction],
    server_error_min: int,
    triage: Path,
    server_log: str = "",
    source_root: Path | None = None,
) -> FaultFunnel:
    candidates, failures = unique_failures(spec, interactions, server_error_min)
    verdicts, causes = load_triage(triage)
    known = {f.signature for f in failures}
    return FaultFunnel(
        candidate_calls=candidates,
        unique_failures=failures,
        verdicts={s: v for s, v in verdicts.items() if s in known},
        root_causes={s: c for s, c in causes.items() if s in known},
        crash_locations=crash_locations(server_log, source_root) if source_root else {},
    )
