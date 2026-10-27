# Work in progress (updated 2026-10-21)

## Done
- Config, OpenAPI model, recording proxy, coverage readers (coverage.py, JaCoCo)
- Benchmark manifest with 6 pinned suites; fetch/verify; service runtime (local processes)
- Metrics: operation coverage, fault funnel + triage, suite quality, retention, mutation
  score, repairs, cost; statistics; measure; comparison report
- Baselines: Schemathesis CLI (application), Hypothesis pytest suite (library),
  EvoMaster 6.2.0 black-box with Python output (search-based)
- End-to-end smoke on booking (3 seeds × 3 tools): `results/summary/smoke-booking.md`
- Literature: vault folder renamed into numbered categories + `00 - Okuma Sırası.md`;
  bib/matrix synced (31 papers); `docs/literature/verified-sources.md`

- Representation layer (`src/restgen/core/representation/`): method-neutral input positions
  (no genes/food sources), operation templates, URI-based resource dependencies;
  `restgen spec inspect`
- JVM service support (optional route): `launch.kind = "jvm"`, JaCoCo, `make toolchain`;
  five WFD services in the manifest (4 verified running, proxyprint fails at startup)

## Next
1. Python benchmark (owner decision 2026-10-21): select WAFP Python targets
   (Flask/Django/Tornado) and the RESTestBench FastAPI service; register them as
   `command` services under coverage.py
2. (Java is not pursued; JVM support stays as is)
3. RESTestBench: requirement-based mutation runner feeding `evaluation/mutation.py`
4. Settle the open protocol questions (budget parity, repetitions, roles) and freeze
   `docs/EXPERIMENT_PROTOCOL.md`
5. Owner confirms D1 = A
