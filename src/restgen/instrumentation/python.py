"""Live Python white-box feedback for search-time fitness.

coverage.py remains the authority for reported experiment coverage. This module has a
different job: provide low-latency guidance after each candidate. A trace hook reports
reached lines and exceptions, while an AST transform adds branch-distance probes to
conditions. The split avoids repeatedly stopping coverage.py and reading its data file.
"""

from __future__ import annotations

import ast
import contextvars
import math
import sys
import threading
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType, TracebackType
from typing import Any


@dataclass
class TargetRecorder:
    """Maximum score observed for each target during one candidate execution."""

    scores: dict[str, float] = field(default_factory=dict)
    state_accesses: dict[str, set[str]] = field(default_factory=dict)

    def observe(self, target: str, score: float) -> None:
        if not 0.0 <= score <= 1.0:
            raise ValueError("observation score must lie within 0..1")
        self.scores[target] = max(score, self.scores.get(target, 0.0))

    def state_access(self, operation: str, resource: str) -> None:
        self.state_accesses.setdefault(operation, set()).add(resource)


_RECORDER: contextvars.ContextVar[TargetRecorder | None] = contextvars.ContextVar(
    "restgen_target_recorder", default=None
)


class PythonInstrumentation(AbstractContextManager[TargetRecorder]):
    """Collect line/exception targets under ``source_roots`` in the current thread."""

    def __init__(self, source_roots: Sequence[Path]) -> None:
        self.roots = tuple(path.resolve() for path in source_roots)
        self.recorder = TargetRecorder()
        self._token: contextvars.Token[TargetRecorder | None] | None = None
        self._previous: Any = None

    def __enter__(self) -> TargetRecorder:
        self._token = _RECORDER.set(self.recorder)
        self._previous = sys.gettrace()
        sys.settrace(self._trace)
        threading.settrace(self._trace)
        return self.recorder

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        sys.settrace(self._previous)
        threading.settrace(None)
        if self._token is not None:
            _RECORDER.reset(self._token)

    def _trace(self, frame: FrameType, event: str, arg: Any) -> Any:
        path = Path(frame.f_code.co_filename)
        if not self._included(path):
            return self._trace
        name = self._name(path)
        if event == "line":
            self.recorder.observe(f"line:{name}:{frame.f_lineno}", 1.0)
        elif event == "exception":
            exception_type = arg[0]
            self.recorder.observe(
                f"exception:{name}:{frame.f_lineno}:{exception_type.__name__}", 1.0
            )
        return self._trace

    def _included(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        return any(resolved.is_relative_to(root) for root in self.roots)

    def _name(self, path: Path) -> str:
        resolved = path.resolve()
        for root in self.roots:
            if resolved.is_relative_to(root):
                return resolved.relative_to(root).as_posix()
        return resolved.as_posix()


def state_access(operation: str, resource: str) -> None:
    """Hook for repositories/ORM listeners to expose Python-side state dependencies."""
    recorder = _RECORDER.get()
    if recorder is not None:
        recorder.state_access(operation, resource)


def normalized(distance: float) -> float:
    if distance < 0 or math.isnan(distance):
        raise ValueError("branch distance must be a non-negative number")
    return 1.0 / (1.0 + distance)


def branch_distances(left: Any, operator: str, right: Any) -> tuple[bool, float, float]:
    """Return predicate result and distances for its true and false outcomes."""
    result = _apply(left, operator, right)
    if operator in {"Eq", "NotEq"}:
        equal_distance = _difference(left, right)
        not_equal_distance = 0.0 if left != right else 1.0
        true_distance, false_distance = (
            (equal_distance, not_equal_distance)
            if operator == "Eq"
            else (not_equal_distance, equal_distance)
        )
    elif _numeric(left, right):
        a, b = float(left), float(right)
        distances = {
            "Lt": (max(0.0, a - b + 1.0), max(0.0, b - a)),
            "LtE": (max(0.0, a - b), max(0.0, b - a + 1.0)),
            "Gt": (max(0.0, b - a + 1.0), max(0.0, a - b)),
            "GtE": (max(0.0, b - a), max(0.0, a - b + 1.0)),
        }
        true_distance, false_distance = distances.get(
            operator, (0.0 if result else 1.0, 1.0 if result else 0.0)
        )
    else:
        true_distance, false_distance = (0.0, 1.0) if result else (1.0, 0.0)
    return result, true_distance, false_distance


def probe_compare(left: Any, operator: str, right: Any, target: str) -> bool:
    result, true_distance, false_distance = branch_distances(left, operator, right)
    recorder = _RECORDER.get()
    if recorder is not None:
        recorder.observe(f"branch:{target}:true", 1.0 if result else normalized(true_distance))
        false_score = 1.0 if not result else normalized(false_distance)
        recorder.observe(f"branch:{target}:false", false_score)
    return result


def probe_bool(value: Any, target: str) -> bool:
    result = bool(value)
    recorder = _RECORDER.get()
    if recorder is not None:
        recorder.observe(f"branch:{target}:true", 1.0 if result else 0.0)
        recorder.observe(f"branch:{target}:false", 1.0 if not result else 0.0)
    return result


def instrument_source(source: str, filename: str) -> Any:
    """Compile source with stable condition probes; the original source is unchanged."""
    tree = ast.parse(source, filename=filename)
    transformed = _ConditionTransformer(filename).visit(tree)
    ast.fix_missing_locations(transformed)
    return compile(transformed, filename, "exec")


def instrumentation_globals() -> dict[str, Any]:
    return {"__restgen_compare__": probe_compare, "__restgen_bool__": probe_bool}


class _ConditionTransformer(ast.NodeTransformer):
    def __init__(self, filename: str) -> None:
        self.filename = filename

    def visit_If(self, node: ast.If) -> ast.AST:
        self.generic_visit(node)
        if not _is_probe(node.test):
            node.test = self._bool_probe(node.test)
        return node

    def visit_While(self, node: ast.While) -> ast.AST:
        self.generic_visit(node)
        if not _is_probe(node.test):
            node.test = self._bool_probe(node.test)
        return node

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if len(node.ops) != 1:
            return node
        target = self._target(node)
        call = ast.Call(
            func=ast.Name(id="__restgen_compare__", ctx=ast.Load()),
            args=[
                node.left,
                ast.Constant(type(node.ops[0]).__name__),
                node.comparators[0],
                ast.Constant(target),
            ],
            keywords=[],
        )
        return ast.copy_location(call, node)

    def _bool_probe(self, node: ast.expr) -> ast.expr:
        call = ast.Call(
            func=ast.Name(id="__restgen_bool__", ctx=ast.Load()),
            args=[node, ast.Constant(self._target(node))],
            keywords=[],
        )
        return ast.copy_location(call, node)

    def _target(self, node: ast.AST) -> str:
        line = getattr(node, "lineno", 0)
        column = getattr(node, "col_offset", 0)
        return f"{self.filename}:{line}:{column}"


def _is_probe(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"__restgen_compare__", "__restgen_bool__"}
    )


def _numeric(left: Any, right: Any) -> bool:
    return (
        isinstance(left, int | float)
        and not isinstance(left, bool)
        and isinstance(right, int | float)
        and not isinstance(right, bool)
    )


def _difference(left: Any, right: Any) -> float:
    if _numeric(left, right):
        return abs(float(left) - float(right))
    if isinstance(left, str) and isinstance(right, str):
        return float(_levenshtein(left, right))
    return 0.0 if left == right else 1.0


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, 1):
        current = [row]
        for column, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _apply(left: Any, operator: str, right: Any) -> bool:
    if operator == "Eq":
        return bool(left == right)
    if operator == "NotEq":
        return bool(left != right)
    if operator == "Lt":
        return bool(left < right)
    if operator == "LtE":
        return bool(left <= right)
    if operator == "Gt":
        return bool(left > right)
    if operator == "GtE":
        return bool(left >= right)
    if operator == "Is":
        return left is right
    if operator == "IsNot":
        return left is not right
    if operator == "In":
        return bool(left in right)
    if operator == "NotIn":
        return bool(left not in right)
    raise ValueError(f"unsupported comparison operator: {operator}")
