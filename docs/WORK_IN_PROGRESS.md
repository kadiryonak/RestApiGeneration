# Work in progress (paused 2026-10-17)

Request: build benchmark + metric infrastructure (owner's pasted analysis, sections 3-7),
with Schemathesis (application) and Hypothesis (library) as comparison tools; organise the
literature folder.

## Done
- `config.py` + `configs/restgen.toml` (budget, seeds, evaluation, proxy, tool paths)
- `openapi.py` (operation = METHOD + path template, URL→template matching, $ref inlining)
- `errors.py`, `jsonio.py`; deps httpx, PyYAML

## Next (in order)
1. Tests for config.py and openapi.py
2. `traffic/` recording reverse proxy (JSONL of every request/response; tool-agnostic)
3. `benchmark/` manifest (`configs/benchmark.toml`): RESTgym, WebFuzzing/Dataset (EMB),
   web-api-fuzzing-project, RESTestBench, PRAB, pinned commits; fetch/verify; service runner
4. `coverage/` coverage.py JSON + JaCoCo XML parsers (line/branch/method, covered sets)
5. `evaluation/`: operation coverage (C_attempt, C_success), test-suite stages (syntax,
   collectable, oracle reached, pass, rerun stability), exploration vs output coverage +
   retention ratio, fault funnel (candidates → dedup → verified → root causes), mutation
   score (response vs implementation families kept apart), cost, statistics
   (Mann-Whitney U, Wilcoxon, Holm, A12, bootstrap CI, project-equal mean), report
6. `baselines/`: schemathesis CLI (benchmarking.md flags, --report junit,har,ndjson,json,wfc),
   hypothesis pytest generator (hypothesis + hypothesis-jsonschema, persistent test module)
7. `runner.py` + CLI; end-to-end smoke on schemathesis/examples/booking under coverage.py
8. Literature (vault `RestApi/RestApi/RESTapiLiteratür/`): rename PDFs to "NN - Title",
   category folders, reading order note, list of papers to download (verify metadata
   online first), sync references.bib + extraction-matrix.csv
9. Update RESEARCH_PLAN (D1 provisionally A: test generation) and the CLAUDE.md phase gate
