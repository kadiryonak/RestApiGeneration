"""Execute structured candidates against a real API and produce search fitness."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import httpx

from restgen.abc.models import Fitness
from restgen.core.representation.testcase import TestCase
from restgen.core.representation.values import ABSENT
from restgen.instrumentation.python import PythonInstrumentation, TargetRecorder


class RestFitnessEvaluator:
    """Fitness adapter; every action is a real HTTP request to ``base_url``."""

    def __init__(
        self,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float,
        source_roots: Sequence[Path] = (),
        stop_on_failure: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers)
        self.timeout = timeout
        self.source_roots = tuple(source_roots)
        self.stop_on_failure = stop_on_failure

    def __call__(self, candidate: TestCase) -> Fitness:
        scores: dict[str, float] = {}
        errors: set[str] = set()
        responses: list[Any] = []
        instrumentation = (
            PythonInstrumentation(self.source_roots)
            if self.source_roots
            else nullcontext(TargetRecorder())
        )
        with instrumentation as recorder, httpx.Client(timeout=self.timeout) as client:
            for index, action in enumerate(candidate.actions):
                try:
                    request = candidate.request(index, responses)
                except Exception as exc:
                    errors.add(f"harness:{type(exc).__name__}")
                    break
                client.cookies.clear()
                client.cookies.update(dict(request.cookies))
                request_headers = {**self.headers, **dict(request.headers)}
                if request.body is ABSENT:
                    response = client.request(
                        request.method,
                        self.base_url + request.path,
                        params=request.query,
                        headers=request_headers,
                    )
                else:
                    response = client.request(
                        request.method,
                        self.base_url + request.path,
                        params=request.query,
                        headers=request_headers,
                        json=request.body,
                    )
                target = f"status:{action.operation.key}:{response.status_code}"
                scores[target] = 1.0
                if response.status_code >= 500:
                    digest = hashlib.sha256(response.content).hexdigest()[:12]
                    errors.add(f"{action.operation.key}:{response.status_code}:{digest}")
                try:
                    responses.append(response.json())
                except ValueError:
                    responses.append(None)
                if self.stop_on_failure and response.status_code >= 400:
                    break
        for target, score in recorder.scores.items():
            scores[target] = max(score, scores.get(target, 0.0))
        return Fitness.from_scores(scores, frozenset(errors))
