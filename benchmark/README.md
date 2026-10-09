# Benchmark

Not chosen yet (Decision D3 in `docs/RESEARCH_PLAN.md`, depends on D1).

Requirements for whatever is chosen, following ABACUS:

1. A manifest in `configs/benchmark.toml` pins every service/project to an
   exact version (tag or commit) and records why it is included.
2. A setup command recreates `benchmark/projects/` (git-ignored) from the
   manifest — clone, install / build (Docker if needed), start, health-check.
3. A verify command proves the installed service is the pinned one and that it
   answers (and, for white-box measurement, that coverage instrumentation works).
4. Results of the verification are written next to each service.
