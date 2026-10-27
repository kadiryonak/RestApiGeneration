# Research plan

**Current phase: 1 — literature review** (started 2026-10-09)

Benchmark and evaluation infrastructure was built ahead of phase 2 at the owner's
request (2026-10-17 / 2026-10-19), assuming D1 = A (see below).
The test-case representation (`src/restgen/core/representation/`: values, HTTP actions,
test cases with references to earlier responses) was built ahead of phase 2 at the
owner's request (2026-10-27). It is method-neutral; no search code exists yet.

## Phases

| # | Phase | Exit criterion |
|---|-------|----------------|
| 1 | Literature review | Protocol in `literature/README.md` executed; extraction matrix complete; gap stated in one paragraph; **Decision D1 taken** |
| 2 | Problem definition & method design | Research questions final; solution encoding, fitness, bee operators and LLM role written down; benchmark and baselines chosen |
| 3 | Protocol freeze | `EXPERIMENT_PROTOCOL.md` filled and dated before any real run |
| 4 | Implementation | `make check` green; smoke run on one benchmark service |
| 5 | Experiments | All protocol runs done; summaries in `results/summary/` |
| 6 | Analysis & writing | Statistics per protocol; thesis chapters |

## Open decisions

### D1 — what is generated? (decide at the end of phase 1)

| | A: REST API **test** generation | B: REST API **implementation** generation |
|---|---|---|
| Input | OpenAPI spec (black-box) and/or source (white-box) of a running service | Natural-language requirements and/or an OpenAPI spec |
| Food source (candidate solution) | A test suite / sequence of HTTP calls with parameter values | A candidate implementation (e.g. FastAPI app, or per-endpoint handlers) |
| Fitness | Operation / status-code coverage, code coverage, 5xx faults found, schema violations | Share of spec-derived tests passed, schema conformance, static quality |
| LLM role | Realistic parameter values, inter-parameter dependencies, call ordering, oracle generation | Generating and repairing handler code, neighbour solutions (`v_ij` analogue) |
| Typical baselines | EvoMaster, RESTler, Schemathesis, ARAT-RL, AutoRestTest, LlamaRestTest | LLM-only generation, LLM + self-repair, GA/random search with the same LLM |
| Fit with vault literature | Strong (all five seed papers) | Weak so far — needs its own search |

Record the decision here with the date and the reasons (what the review showed).

**Provisional (2026-10-19): A — the owner's benchmark/metric analysis targets a
persistent Python test suite for existing REST APIs, and the infrastructure is built for
that. To be confirmed by the owner at the end of phase 1.**

### D2 — LLM provider(s)
API (DeepSeek/OpenAI/Claude) vs. local (Ollama). Driven by budget and by the
model-independence question; decide in phase 2.

### D3 — benchmark

**Owner decision (2026-10-21): the main benchmark is Python services.** The JVM route
(WFD/EMB jars built with a pinned JDK 8 + Maven, JaCoCo coverage) is implemented and was
checked on the five EvoMaster-study services (features-service, catwatch, rest-news,
scout-api start and are measured; proxyprint fails at startup: it needs a writable
documents directory). It stays available but is not pursued further. Python candidates
with a paper behind them: the Python targets of WAFP (Schemathesis, ICSE 2022) and the
FastAPI service of RESTestBench (EASE 2026).

Candidates are pinned in `configs/benchmark.toml` (RESTgym, WFD/EMB, WAFP, RESTestBench,
PRAB). Proposed composition (owner's analysis §6.3): 8–11 RESTgym/WFD services as the
comparable main group, 4–6 WAFP services for technology diversity, the three RESTestBench
services for requirement-based fault detection, a few artificial APIs for mechanism
studies. Not frozen; online APIs are not used as the main reproducible benchmark.

## Candidate research questions (to be finalised in phase 2)

- **RQ1 (effectiveness):** Does the ABC + LLM hybrid outperform the
  state-of-the-art baselines on the chosen metrics?
- **RQ2 (hybrid vs. parts):** How does it compare to pure ABC (no LLM) and to
  the LLM alone with the same budget?
- **RQ3 (ablation):** What does each component contribute (LLM in employed
  phase, onlooker phase, scout phase; selection scheme; `limit`)?
- **RQ4 (cost/efficiency):** Coverage or quality per LLM call / token / USD /
  wall-clock time.
- **RQ5 (sensitivity / model independence):** Sensitivity to ABC parameters
  (colony size SN, `limit`, MCN) and to the chosen LLM.

## ABC reference (Karaboga 2005; Karaboga & Basturk 2007)

- SN food sources = candidate solutions; colony = SN employed + SN onlooker bees.
- **Employed phase:** each bee makes a neighbour `v_ij = x_ij + φ_ij (x_ij − x_kj)`;
  greedy selection; failure increments the source's trial counter.
- **Onlooker phase:** sources chosen with probability proportional to fitness,
  then the same neighbour search.
- **Scout phase:** a source whose trial counter exceeds `limit` is abandoned and
  replaced by a new random one.
- Stop after MCN cycles (or an evaluation/budget limit).
- For discrete/structured solutions (test sequences, code) the neighbour
  operator must be redefined — this is where the LLM is expected to enter.
  The review should collect how discrete ABC variants and LLM-as-operator
  works (e.g. LLM-driven evolutionary search) define it.
