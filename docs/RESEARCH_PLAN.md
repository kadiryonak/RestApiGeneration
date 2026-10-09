# Research plan

**Current phase: 1 — literature review** (started 2026-10-09)

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

### D2 — LLM provider(s)
API (DeepSeek/OpenAI/Claude) vs. local (Ollama). Driven by budget and by the
model-independence question; decide in phase 2.

### D3 — benchmark
Depends on D1. Candidates to evaluate in phase 1: EMB (EvoMaster Benchmark),
the service sets used by ARAT-RL / AutoRestTest / LlamaRestTest, RESTgym.
Must be pinned and reproducible (`benchmark/README.md`).

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
