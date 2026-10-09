# AGENTS.md

Guidance for any coding agent (and human) working in this repository.

## What restgen is

restgen is the implementation behind a graduation thesis by Kadir Yönak: a
**hybrid of the Artificial Bee Colony (ABC) algorithm and large language
models (LLMs) for REST APIs**. ABC (Karaboga, 2005) provides the population
based search (employed / onlooker / scout bees, `limit`, fitness-proportional
selection); the LLM provides domain knowledge as a variation or construction
operator inside that search.

**Current phase: literature review.** No method code is written yet. The exact
problem — generating *tests* for an existing REST API vs. generating the *API
implementation* itself — is decided at the end of the review and recorded in
[`docs/RESEARCH_PLAN.md`](docs/RESEARCH_PLAN.md). Until then do not add method
code, dependencies or a package layout that presumes one of the two directions.

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
  EXPERIMENT_PROTOCOL.md  frozen before the first real run; change log afterwards
  literature/           review protocol, BibTeX, extraction matrix, note template
configs/                experiment configuration (TOML); experiments/ holds variants
src/restgen/            the package (empty until the method is fixed)
tests/unit              fast, no network, no subprocess
tests/integration       real services / subprocesses (marker: integration)
tests/support           shared fakes and fixtures (e.g. a scripted fake LLM client)
benchmark/              benchmark manifest docs; checked-out services are git-ignored
results/                experiment output (raw runs git-ignored, summary/ committed)
scripts/                one-off orchestration (experiment chains), not library code
schemathesis/           upstream Schemathesis clone for study (git-ignored, own .venv;
                        never install restgen deps there or Schemathesis into restgen's .venv)
hypothesis/             upstream Hypothesis clone for study (git-ignored, partial clone)
```

The sub-package layout of `src/restgen/` is designed after the literature
review. Expected building blocks, whichever direction is chosen: `config`,
`errors`, `cli`, an `abc/` search core (food source, colony, bee phases,
selection, termination), an `llm/` layer (clients, prompts, caching, cost
accounting), a `benchmark/` layer, an `evaluation/` layer (metrics, statistics,
reports) and `baselines/`.

## Commands

```bash
make install          # .venv (Python 3.12, uv) with restgen + dev tools
source .venv/bin/activate
make check            # ruff + ruff format --check + mypy --strict + unit tests
make test-integration # tests marked integration
make format           # auto-fix lint and formatting
```
