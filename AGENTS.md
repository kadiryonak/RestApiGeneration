# AGENTS.md

Guidance for any coding agent (and human) working in this repository.

## What restgen is

restgen is the implementation behind a graduation thesis by Kadir Yönak: a
**hybrid of the Artificial Bee Colony (ABC) algorithm and large language
models (LLMs) for REST APIs**. ABC (Karaboga, 2005) provides the population
based search (employed / onlooker / scout bees, `limit`, fitness-proportional
selection); the LLM provides domain knowledge as a variation or construction
operator inside that search.

**Current phase: literature review**, with the benchmark and evaluation
infrastructure already built at the owner's request (2026-10-17). It assumes
direction A of decision D1 (generating a persistent Python *test suite* for an
existing REST API); see [`docs/RESEARCH_PLAN.md`](docs/RESEARCH_PLAN.md). The
ABC + LLM *method* itself (`src/restgen/abc/`, `src/restgen/llm/`) is not written
until the phase changes.

## Measurement architecture

Every tool (the method and every baseline) is measured the same way:

1. the service runs fresh, in its own venv, under a coverage tool;
2. the tool talks to it **only through the recording proxy**
   (`traffic/proxy.py`), which writes every exchange to `traffic.jsonl`;
3. a tool that produces a test suite has it re-run alone on clean services
   (output coverage, retention, stability);
4. `restgen measure` computes `metrics.json` from the recorded artefacts only.

The proxy port is fixed for a whole run, so suites that hard-code the URL they were
generated against (EvoMaster) reach the clean services of the re-runs too. Tools that
keep state between runs (Schemathesis' crash cache, EvoMaster's working files) run with
the run's own `tool/` directory as working directory, so repetitions stay independent.

Metric definitions live in the module docstrings of `src/restgen/evaluation/`
(operation coverage, faults, suite quality, retention, mutation, repairs, cost,
statistics). Undefined values are `None`, never a fake 0 or 1.

## Non-negotiable rules

- **Real measurements only.** Every reported number (coverage, status codes,
  faults found, tests passed, cost) must come from actually running the code
  under evaluation against a real service. Never mock the system under test in
  an evaluation, never report a metric that was not produced by a recorded run.
- **English identifiers everywhere** – files, modules, classes, functions,
  variables, log messages, repository docs. Research notes may be Turkish;
  code may not.
- **OOP with small, typed units.** Frozen dataclasses for data, ABCs for
  extension points (LLM clients, bee operators, fitness functions, benchmark
  adapters). `mypy --strict` and `ruff` must pass.
- **Every step ships with tests.** A feature is not done until its unit tests
  pass; anything touching subprocesses, Docker or benchmark services gets an
  `integration` test; anything calling a real LLM gets a `network` test.
- **Config is the single source of truth.** Experiment parameters (colony
  size, `limit`, max cycles, model, temperature, budgets, seeds) live in
  `configs/*.toml`; do not hard-code them.
- **Seeds and budgets are explicit.** ABC is stochastic and LLMs are costly:
  every run records its seed, its resolved config and its token/USD/time spend.
- **Secrets** only via `.env`. Never commit `.env`.
- **Commits** are authored by the repository owner only. Do not add AI
  attribution, `Co-Authored-By` trailers or tool names to commit messages or
  PR descriptions.

## Layout

```
docs/
  RESEARCH_PLAN.md      thesis phases, open decisions, candidate research questions
  LAB_NOTEBOOK.md       dated log of everything tried, found and decided (paper material)
  EXPERIMENT_PROTOCOL.md  frozen before the first real run; change log afterwards
  literature/           review protocol, BibTeX, extraction matrix, note template
configs/                experiment configuration (TOML); experiments/ holds variants
src/restgen/
  config.py, errors.py, cli.py, openapi.py, runner.py
  traffic/              recording reverse proxy + interaction model
  benchmark/            manifest registry, pinned suite fetcher, service runtime
  coverage/             coverage.py JSON and JaCoCo XML readers (covered sets kept)
  evaluation/           metrics, measure (metrics.json), statistics, comparison report
  baselines/            comparison tools: Schemathesis CLI, Hypothesis pytest suite,
                        EvoMaster black-box (Python unittest output)
tests/unit              fast, no network, no subprocess
tests/integration       real services / subprocesses (marker: integration)
tests/support           shared fakes and fixtures (e.g. a scripted fake LLM client)
benchmark/              benchmark manifest docs; checked-out services are git-ignored
results/                experiment output (raw runs git-ignored, summary/ committed)
scripts/                one-off orchestration (experiment chains), not library code
schemathesis/           upstream Schemathesis clone for study (git-ignored, own .venv;
                        never install restgen deps there or Schemathesis into restgen's .venv)
hypothesis/             upstream Hypothesis clone for study (git-ignored, partial clone)
.venvs/hypothesis/      Hypothesis baseline environment (`make tools`, git-ignored)
.venvs/evomaster/       runs EvoMaster's generated Python tests (`make tools`, git-ignored)
.tools/evomaster/       EvoMaster release jar, checksum-verified (`make tools`, git-ignored)
```

Still to come with the method: an `abc/` search core (food source, colony, bee
phases, selection, termination) and an `llm/` layer (clients, prompts, caching,
cost accounting). The method plugs in as one more `ComparisonTool`.

## Commands

```bash
make install          # .venv (Python 3.12, uv) with restgen + dev tools
source .venv/bin/activate
make check            # ruff + ruff format --check + mypy --strict + unit tests
make test-integration # tests marked integration
make format           # auto-fix lint and formatting
make tools            # Schemathesis, Hypothesis (pinned clones) and EvoMaster (release jar)

restgen benchmark list|fetch|verify      # suites at pinned commits
restgen benchmark setup -s booking       # service venv
restgen run --run-id NAME -s booking -t schemathesis -t hypothesis -t evomaster [--seed N] [--force]
restgen measure results/runs/NAME/...    # recompute metrics.json (e.g. after triage)
restgen report --name NAME --group a='NAME/*/schemathesis/*' --group b='NAME/*/hypothesis/*'
restgen --set budget.max_time_seconds=600 run ...   # config overrides
```

After a run, label every failure in its `triage.toml` (`app_bug` with a
`root_cause` id, `tool_assumption` or `environment`); verified bug counts stay
`null` until triage is complete.
