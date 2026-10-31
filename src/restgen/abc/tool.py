"""ComparisonTool adapter that runs DABC-HS and emits a persistent pytest suite."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from restgen.abc.codegen import pytest_suite
from restgen.abc.dependencies import DependencyGraph
from restgen.abc.engine import DabcHs, DabcHsConfig
from restgen.abc.fitness import RestFitnessEvaluator
from restgen.abc.rest import RestTestOperator
from restgen.baselines.base import PytestSuiteTool, ToolRunContext, ToolRunResult
from restgen.config import DabcHsSettings
from restgen.core.representation.templates import build_templates
from restgen.core.representation.testcase import TestCase
from restgen.openapi import OpenApiSpec


class DabcHsTool(PytestSuiteTool):
    name = "dabc-hs"

    def __init__(self, settings: DabcHsSettings, spec: OpenApiSpec) -> None:
        self.settings = settings
        self.spec = spec

    @property
    def python(self) -> Path:
        return Path(sys.executable)

    def version(self) -> str:
        return "restgen-dabc-hs/0.1"

    def run(self, context: ToolRunContext) -> ToolRunResult:
        started = time.perf_counter()
        context.output_dir.mkdir(parents=True, exist_ok=True)
        templates = build_templates(self.spec)
        graph = DependencyGraph(templates)
        operator = RestTestOperator(
            templates,
            graph,
            self.settings.smart_sampling_rate,
            self.settings.mutation_rate,
            self.settings.max_test_actions,
        )
        config = DabcHsConfig(
            self.settings.population_size,
            self.settings.limit,
            self.settings.archive_size,
            self.settings.mutation_threshold,
            self.settings.min_mutations,
            self.settings.max_mutations,
            self.settings.size_factors,
            self.settings.change_number,
            self.settings.reset_number,
            context.budget.max_examples,
            float(context.budget.max_time_seconds),
        )
        result = DabcHs(
            config,
            operator,
            RestFitnessEvaluator(
                context.base_url,
                context.headers,
                context.budget.request_timeout_seconds,
                stop_on_failure=True,
            ),
            len,
            context.seed,
        ).run()
        cases: list[TestCase] = []
        seen: set[int] = set()
        for target in sorted(result.archive.targets):
            for individual in result.archive.population(target):
                identity = id(individual.candidate)
                if identity not in seen:
                    seen.add(identity)
                    cases.append(individual.candidate)
        suite = context.output_dir / "test_dabc_hs_generated.py"
        suite.write_text(pytest_suite(cases), encoding="utf-8")
        return ToolRunResult(
            tool=self.name,
            version=self.version(),
            command=("in-process", "dabc-hs"),
            exit_code=0,
            wall_seconds=time.perf_counter() - started,
            tests=(suite,),
            reports={},
        )
