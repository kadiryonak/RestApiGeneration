# Metrics: what the literature measures and how restgen implements it

Extracted on 2026-10-21 from the paper texts (page numbers are PDF pages). Where a paper
leaves a definition open, that is stated, and restgen's choice is marked as ours.
Implementation: module in `src/restgen/evaluation/` (key in `metrics.json`).

## Coverage of the service's code

| Metric | Papers | Definition | restgen |
|---|---|---|---|
| Line / branch / method coverage | Kim ISSTA'22 §4.2; AutoRestTest §V-A; LlamaRestTest §4.1; RESTgym §III-D; RESTifAI §3; WFC §6; Open Problems §4.2 (line); Zhang EMSE'21 §8.1 | covered / total, JaCoCo (JVM), c8 (Node); service's own code | `coverage/` (coverage.py, JaCoCo on own packages) → `exploration_coverage` |
| Coverage during fuzzing vs of the generated tests | Open Problems §4.2 (during fuzzing); WFC §6.2 Table 10 (base boot B, fuzzing X, tests Y; EvoMaster 45.5 % → 37.1 %) | measure both, labelled | `exploration_coverage`, `output_coverage`, `retention` (`retention.py`) |
| Coverage over time / over requests | Kim'22 (10-min increments); RESTgym (over time and over #requests; samples must not decrease); Open Problems (6 min / 1 h / 10 h) | cumulative, non-decreasing | operation-level curves over time and over requests (`timeline.py`); code coverage only at the end (coverage.py cannot be sampled mid-run) |

## Coverage of the API (black-box)

| Metric | Papers | Definition | restgen |
|---|---|---|---|
| Operation coverage (2xx) | RESTgym §III-D: covered when ≥ 1 response is 2XX; WFC §6 (1): % endpoints with ≥ 1 2xx; RESTifAI #OC; AutoRestTest/LlamaRestTest "successfully processed operations" (undefined in text; 2xx implied) | operation = method + path template | `operation_success_coverage` (`operations.py`) |
| Operation coverage (request sent) | Martin-Lopez A-TEST'19 §3.1 | ≥ 1 request, any status | `operation_attempt_coverage` |
| Path coverage | Martin-Lopez §3.1 | paths with ≥ 1 request / paths | `criteria.py` |
| Parameter coverage | Martin-Lopez §3.1 | (operation, parameter) pairs used / all; path, query, header and body count; no combinations | `criteria.py` |
| Parameter value coverage | Martin-Lopez §3.1 | only boolean and enum parameters: distinct values sent / all possible values | `criteria.py` |
| Input content-type coverage | Martin-Lopez §3.1 | over operations with a body: request content-types used / declared | `criteria.py` |
| Operation flow coverage | Martin-Lopez §3.1 (simplified Arcuri flows) | per creatable resource: create→read one, create→read all, create→update, create→delete | `criteria.py` (black-box approximation: second step after a successful create, in time order) |
| Status code class coverage | Martin-Lopez §3.2, §5.2 | classes "correct" (2XX) and "erroneous" (4XX/5XX), max two per operation / 2 × operations | `criteria.py` |
| Status code coverage | Martin-Lopez §3.2; EvoMaster TOSEM'19 (statuses per endpoint as targets); WFC `coveredHttpStatus` | documented (operation, code) pairs obtained / documented pairs (denominator implied in the paper) | `criteria.py`, plus all observed statuses per operation in `operations.status_classes` |
| Response body property coverage | Martin-Lopez §3.2 | properties present in received bodies / all properties of all response schemas | `criteria.py` (bodies above `proxy.max_body_bytes` are not parsed and are counted) |
| Output content-type coverage | Martin-Lopez §3.2 | response content-types obtained / declared | `criteria.py` |
| Test Coverage Level (TCL) | Martin-Lopez §4 | cumulative: L1 path, L2 operation, L3 content-types, L4 parameter + status class, L5 parameter value + status code, L6 response properties, L7 flows | `criteria.py` |

## Faults

| Metric | Papers | Definition | restgen |
|---|---|---|---|
| Operations with a 500 / 5xx | WFC §6 (2): endpoints with ≥ 1 500; EvoMaster TOSEM'19 §6.3: failing endpoints (5xx) as fault estimate; Martin-Lopez §5: operation with ≥ 1 5XX | count of operations | `faults.operations_with_500`, `faults.operations_with_5xx` |
| Unique failures by message | AutoRestTest, LlamaRestTest (ARAT-RL script: per operation, dedup by server response message); RESTgym (Jaccard buckets, per-API threshold, untuned) | | `faults.unique_failures` (operation + status + normalised message) |
| Unique failures by code location | Hatfield-Dodds & Dygalo ICSE'22 §3.1 (Sentry; by code location, regardless of endpoint); Kim'22 §4 (unique failure points = top method-line of the stack trace; library failure points) | | `faults.unique_crash_locations` (innermost service frame), `faults.failure_points` / `library_failure_points` (top frame) |
| Verified bugs / root causes | Agentic PBT (manual validity, κ, CI); RESTifAI (Bug / Enhancement / Invalid) | manual labels | `triage.toml` → `verified_bugs`, `distinct_root_causes` |
| WFC fault identity | WFC §4.2: (category code, endpoint, context) | | not yet: needs a pinned WFC release |
| Seeded-fault detection | Open Problems §4.5 (rest-faults: 10 fault types) | per fault type, detected or not | possible later with a seeded Python API |

## Generated tests

| Metric | Papers | restgen |
|---|---|---|
| Number of tests | EvoMaster'19 Table 2; RESTifAI #TC; WFC `totalTests` | `suite.tests` |
| Run health, "Problem %" = (errors + failures) / tests | WFC §6.2 Table 11 (pytest `--junitxml`) | `suite.problem_rate` |
| Requirements-based mutation score MS = killed / mutants | RESTestBench §3.4 (one test per requirement; valid and mutant-specific variants; kill condition from PBMT, not restated) | `mutation.py` (runner not yet) |
| Syntax / collectable / oracle reached / pass / stable | owner's analysis §5.1 (ours) | `suite.py` |

## Cost and effort

| Metric | Papers | restgen |
|---|---|---|
| Wall-clock time | ICSE'22 Table 8; Agentic PBT; WFC `executionTimeInSeconds` | `cost.wall_seconds` |
| HTTP calls (also as budget: 10k/100k) | EvoMaster'19 §6.2; Zhang EMSE'21; WFC `outputHttpCalls` | `cost.http_calls` |
| LLM tokens in/out, USD (per run, per test, per bug), $/1M prices with model id | RESTestBench Table 4; Agentic PBT; RESTifAI (tokens/test) | `llm/accounting.py` → `llm` (also cached, reasoning, retries, latency, per purpose) |
| Report redundancy (reports per unique defect) | ICSE'22 Table 9 | not yet (needs each tool's own report counts) |

## Statistics

| Practice | Papers | restgen |
|---|---|---|
| Mann-Whitney U + Vargha-Delaney Â12 per service | EvoMaster'19; Zhang EMSE'21; Open Problems; WFC; Schemathesis benchmarking guide | `statistics.py`, `report.py` |
| Friedman over services (ranking of tools) | Open Problems; WFC; Zhang EMSE'21 | `statistics.friedman` |
| Repetitions | 10 typical (Kim'22, AutoRestTest, LlamaRestTest, RESTgym, Open Problems, WFC); 30 (Zhang EMSE'21, ICSE'22); 3 (RESTestBench) | protocol decision |
| Budget | 1 h typical; HTTP-call budgets in EvoMaster'19 / EMSE'21; matched time in RESTifAI | protocol decision |

## Not defined anywhere (restgen's own, labelled as such)
Time to first failure; success-coverage AUC; retention; oracle-reached rate; stability.
