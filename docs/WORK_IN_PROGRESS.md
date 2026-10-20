# Work in progress (updated 2026-10-20)

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

## Next
1. Container launch (Podman) for RESTgym services: JaCoCo agent + XML export; register
   the 11 APIs with their OpenAPI files and health checks
2. Same for WFD / WAFP services chosen for the main group
3. RESTestBench: requirement-based mutation runner feeding `evaluation/mutation.py`
4. Settle the open protocol questions (budget parity, repetitions, roles) and freeze
   `docs/EXPERIMENT_PROTOCOL.md`
5. Owner confirms D1 = A
