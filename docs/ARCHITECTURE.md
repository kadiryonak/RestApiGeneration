# Architecture guide

This is the shortest path for learning the repository. The key rule is that **generation
and measurement are separate systems**. A method may optimize any search fitness, but
thesis numbers are reconstructed later from recorded HTTP traffic, coverage reports and
suite reruns.

```text
OpenAPI + config
      │
      ├── core/representation ──> TestCase / HttpAction / ResponseRef
      │                                  │
      │                                  v
      ├── abc/ ─────────────────> search + generated pytest
      │                                  │
      v                                  v
runner ──> recording proxy ──> fresh benchmark service under coverage
  │                  │                         │
  │                  └── traffic.jsonl         └── coverage.normalized.json
  │
  ├── clean reruns of the generated suite
  └── evaluation/ ──> metrics.json ──> report/statistics
```

## Layer map

| Layer | Responsibility | Must not do |
|---|---|---|
| `config.py`, `configs/` | typed, resolved experiment controls | hide seeds/budgets in code |
| `openapi.py` | load and resolve OpenAPI/Swagger documents | create search candidates |
| `core/representation/` | method-neutral input types, values, requests and test sequences | know ABC, LLM or fitness |
| `abc/` | DABC-HS state, archive, selection, REST operators, live fitness and pytest output | report thesis metrics from its own memory |
| `instrumentation/` | low-latency Python guidance for the search | replace authoritative coverage.py measurement |
| `baselines/` (repository root) | ignored third-party clones, JARs and private environments | contain restgen application code |
| `src/restgen/baselines/` | versioned adapters implementing the common tool interface | vendor third-party source/binaries |
| `benchmark/` | pinned service metadata, setup and clean process lifecycle | choose or favor a search method |
| `traffic/` | transparent reverse proxy and exchange recording | compute final metrics |
| `coverage/` | normalize coverage.py and JaCoCo reports | guide DABC-HS live |
| `runner.py` | orchestrate one `(service, tool, seed)` run and clean reruns | define metric formulas |
| `evaluation/` | reconstruct tool-neutral metrics from immutable artefacts | execute candidates or influence search |
| `telemetry/` | optional method-neutral search event log | serve as coverage evidence |
| `llm/` | usage/cost accounting today; clients/operators later | silently call a model outside the budget |

## Why `evaluation/` is necessary when `abc/` exists

They answer different questions:

- `abc/fitness.py` asks **“which candidate should the search prefer now?”** Its scores
  may include branch-distance gradients, target archive state and heuristic feedback.
- `evaluation/` asks **“what did this completed run actually achieve under the common
  protocol?”** It reads only proxy traffic, coverage artefacts, JUnit files, triage and
  accounting logs. The same code measures DABC-HS, Schemathesis, Hypothesis and
  EvoMaster.

Combining them would let the proposed method grade itself with information unavailable
to baselines, make metric definitions depend on search internals, and violate the
“recorded real measurements only” rule. The similarly named old `abc/evaluation.py` was
renamed to `abc/fitness.py` to make this boundary explicit.

## DABC-HS code reading order

1. `abc/models.py`: target score, fitness vector and evaluated individual.
2. `abc/archive.py`: one bounded population per target and feedback counters.
3. `abc/selection.py`: preference sorting, Pareto fronts and crowding distance.
4. `abc/engine.py`: initialization, employed, onlooker, scout and Hyper-Scout phases.
5. `abc/dependencies.py`: OpenAPI, Python-state and fitness evidence graph.
6. `abc/rest.py`: lifecycle construction, response chaining and structural/value mutation.
7. `abc/fitness.py`: real HTTP execution and live target conversion.
8. `abc/codegen.py`: self-contained persistent pytest output.
9. `abc/tool.py`: bridge to the common `ComparisonTool`/runner contract.

## One run, step by step

1. CLI resolves config, benchmark service, tool and seed.
2. Runner starts a fresh service under coverage and one recording proxy.
3. The tool reads the exact OpenAPI document. DABC-HS builds operation templates and a
   resource dependency graph.
4. Every candidate sends real requests only through the proxy. The search updates its
   target archive; the proxy independently records every exchange.
5. DABC-HS emits archive candidates as pytest. The service stops and coverage is exported.
6. Runner starts fresh service instances and executes only the saved suite for each rerun.
7. `restgen measure` derives operation/status/schema coverage, faults, code coverage,
   suite quality, retention, timeline and cost from those artefacts.
8. `restgen report` compares repeated seeds statistically; it never re-runs a tool.

## Review findings and remaining boundaries

The current structure has no redundant `evaluation`/`abc` subsystem; their separation is
required for fair experiments. The apparent overlaps are intentional adapters:

- `core/representation/resources.py` supplies method-neutral URI facts;
  `abc/dependencies.py` adds search-time evidence and learning.
- `coverage/` reads final reports; `instrumentation/` provides live gradients.
- root `baselines/` stores ignored installations; `src/restgen/baselines/` stores tracked
  adapters.

Work still required before protocol experiments:

- connect live instrumentation/state-access events from a separately launched Python
  service to `RestFitnessEvaluator`; current CLI DABC-HS is status-guided black-box;
- connect DABC-HS phase/evaluation events to the existing `SearchTrace` writer;
- implement the budgeted LLM semantic-value/dependency operator and its cache;
- broaden generated oracles beyond no-5xx where the protocol permits it;
- add ORM/framework integrations for state-access evidence and robust JSONPath array
  handling in generated suites;
- freeze benchmark, information parity, budgets and ablations before any result claim.
