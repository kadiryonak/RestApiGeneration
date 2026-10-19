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
from restgen.errors import RestgenError


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.root.resolve(), args.config, args.overrides)
        if args.command == "config":
            print(json.dumps(settings.to_dict(), indent=2, sort_keys=True))
            return 0
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
        if not fetcher.verify(registry.suite(service.suite)).ok:
            fetcher.fetch(registry.suite(service.suite))
        environment = ServiceEnvironment(service, settings.paths.benchmark_dir)
        environment.setup()
        print(f"{name}: {environment.python}")
    return 0
