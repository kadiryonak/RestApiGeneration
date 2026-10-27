"""The ``restgen`` command line."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from restgen.benchmark.fetcher import SuiteFetcher
from restgen.benchmark.registry import BenchmarkRegistry
from restgen.benchmark.service import ServiceEnvironment
from restgen.config import DEFAULT_CONFIG, Settings, load_settings
from restgen.core.representation.resources import summarize
from restgen.core.representation.templates import build_templates
from restgen.errors import RestgenError
from restgen.evaluation.measure import measure
from restgen.evaluation.report import build_report, collect
from restgen.jsonio import write_json
from restgen.openapi import OpenApiSpec
from restgen.runner import TOOLS, Runner, RunRequest, load_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="restgen", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--set", dest="overrides", action="append", default=[], metavar="SECTION.KEY=VALUE"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("config", help="print the resolved configuration")

    benchmark = commands.add_parser("benchmark", help="benchmark suites and services")
    actions = benchmark.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="suites and services in the manifest")
    fetch = actions.add_parser("fetch", help="check suites out at their pinned commits")
    fetch.add_argument("-s", "--suite", action="append", default=[])
    actions.add_parser("verify", help="check that fetched suites are pinned and unchanged")
    setup = actions.add_parser("setup", help="create service virtualenvs")
    setup.add_argument("-s", "--service", action="append", default=[])

    spec = commands.add_parser("spec", help="OpenAPI documents")
    spec_actions = spec.add_subparsers(dest="action", required=True)
    inspect = spec_actions.add_parser(
        "inspect", help="input positions and resource dependencies of an API"
    )
    target = inspect.add_mutually_exclusive_group(required=True)
    target.add_argument("-s", "--service", help="a service whose OpenAPI is a file in its suite")
    target.add_argument("-f", "--file", type=Path, help="any OpenAPI/Swagger document")
    inspect.add_argument("--templates", action="store_true", help="print every operation")

    run = commands.add_parser("run", help="run tools on services (then measure)")
    run.add_argument("--run-id", required=True)
    run.add_argument("-s", "--service", action="append", required=True)
    run.add_argument("-t", "--tool", action="append", choices=TOOLS, required=True)
    run.add_argument("--seed", type=int, action="append", help="default: repetitions.seeds")
    run.add_argument("--force", action="store_true", help="replace existing run directories")

    measure_cmd = commands.add_parser("measure", help="recompute metrics.json of runs")
    measure_cmd.add_argument("run_dirs", nargs="+", type=Path)

    report = commands.add_parser("report", help="compare groups of runs")
    report.add_argument("--name", required=True)
    report.add_argument(
        "--group",
        action="append",
        required=True,
        metavar="LABEL=GLOB[,GLOB]",
        help="run directories relative to results/runs, e.g. st=smoke/*/schemathesis/*",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.root.resolve(), args.config, args.overrides)
        if args.command == "config":
            print(json.dumps(settings.to_dict(), indent=2, sort_keys=True))
            return 0
        if args.command == "run":
            return _run(settings, args)
        if args.command == "measure":
            return _measure(settings, args.run_dirs)
        if args.command == "report":
            return _report(settings, args)
        if args.command == "spec":
            return _spec(settings, args)
        return _benchmark(settings, args)
    except RestgenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _benchmark(settings: Settings, args: argparse.Namespace) -> int:
    registry = BenchmarkRegistry.load(settings.paths.benchmark_manifest)
    fetcher = SuiteFetcher(settings.paths.benchmark_dir)
    if args.action == "list":
        for suite in registry.suites.values():
            print(f"{suite.name:24} {suite.kind.value:13} {suite.commit[:12]}  {suite.repository}")
            for service in registry.services_of(suite.name):
                print(
                    f"  - {service.name:20} {service.language}/{service.framework} "
                    f"{service.category.value} {service.role.value}"
                )
        return 0
    if args.action == "fetch":
        names = args.suite or list(registry.suites)
        for name in names:
            status = fetcher.fetch(registry.suite(name))
            print(f"{name}: {status.head} at {status.path}")
        return 0
    if args.action == "verify":
        failures = 0
        for suite in registry.suites.values():
            status = fetcher.verify(suite)
            state = (
                "ok"
                if status.ok
                else (
                    "missing"
                    if not status.present
                    else "wrong commit"
                    if not status.pinned
                    else "modified"
                )
            )
            failures += not status.ok
            print(f"{suite.name:24} {state}")
        return 1 if failures else 0
    # setup
    names = args.service or list(registry.services)
    for name in names:
        service = registry.service(name)
        suite = registry.suite(service.suite)
        if not fetcher.verify(suite).ok:
            fetcher.fetch(suite)
        environment = ServiceEnvironment(
            service, settings.paths.benchmark_dir, fetcher.path(suite), settings.toolchain
        )
        environment.setup()
        target = environment.jar if service.launch.jar else environment.python
        print(f"{name}: {target}")
    return 0


def _source_root(settings: Settings, service_name: str) -> Path | None:
    registry = BenchmarkRegistry.load(settings.paths.benchmark_manifest)
    if service_name not in registry.services:
        return None
    service = registry.service(service_name)
    suite_path = SuiteFetcher(settings.paths.benchmark_dir).path(registry.suite(service.suite))
    return (suite_path / service.launch.workdir).resolve()


def _run(settings: Settings, args: argparse.Namespace) -> int:
    runner = Runner(settings, BenchmarkRegistry.load(settings.paths.benchmark_manifest))
    seeds = args.seed or list(settings.repetitions.seeds)
    for service in args.service:
        for tool in args.tool:
            for seed in seeds:
                directory = runner.run(RunRequest(args.run_id, service, tool, seed), args.force)
                metrics = measure(directory, _source_root(settings, service))
                ops = metrics["operations"]
                coverage = metrics["exploration_coverage"] or {}
                print(
                    f"{service}/{tool}/s{seed}: ops success {ops['operation_success_coverage']}, "
                    f"line {coverage.get('line_coverage')}, "
                    f"failures {metrics['faults']['unique_failures']} -> {directory}"
                )
    return 0


def _measure(settings: Settings, run_dirs: list[Path]) -> int:
    for directory in run_dirs:
        service = str(load_run(directory)["service"])
        measure(directory, _source_root(settings, service))
        print(f"measured {directory}")
    return 0


def _report(settings: Settings, args: argparse.Namespace) -> int:
    groups: dict[str, list[str]] = {}
    for spec in args.group:
        label, sep, patterns = spec.partition("=")
        if not sep or not label or not patterns:
            raise RestgenError(f"--group must look like LABEL=GLOB[,GLOB]: {spec!r}")
        groups[label] = patterns.split(",")
    data, categories = collect(settings.paths.results_dir, groups)
    markdown, payload = build_report(args.name, data, categories)
    summary = settings.paths.results_dir / "summary"
    summary.mkdir(parents=True, exist_ok=True)
    (summary / f"{args.name}.md").write_text(markdown + "\n", encoding="utf-8")
    write_json(summary / f"{args.name}.json", payload)
    print(summary / f"{args.name}.md")
    return 0


def _spec(settings: Settings, args: argparse.Namespace) -> int:
    if args.file is not None:
        document = OpenApiSpec.load(args.file)
    else:
        registry = BenchmarkRegistry.load(settings.paths.benchmark_manifest)
        service = registry.service(args.service)
        if not service.openapi_is_file:
            raise RestgenError(f"{service.name}: its OpenAPI is served at run time; use --file")
        suite = SuiteFetcher(settings.paths.benchmark_dir).path(registry.suite(service.suite))
        document = OpenApiSpec.load(suite / service.openapi.removeprefix("file:"))
    templates = build_templates(document)
    output: dict[str, object] = {"openapi": document.version, **summarize(templates)}
    if args.templates:
        output["templates"] = [
            {
                "operation": t.key,
                "media_type": t.media_type,
                "inputs": [
                    {"position": i.key, "required": i.required, **i.spec.describe()}
                    for i in t.inputs
                ],
            }
            for t in templates
        ]
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0
