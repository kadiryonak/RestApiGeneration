# Lab notebook

Dated record of everything tried, found and decided, with the real numbers and where they
came from. It is the raw material for the paper's *Experimental setup*, *Threats to
validity* and *Discussion*. Rules:

- Append; never rewrite history. A wrong earlier claim gets a new entry that corrects it.
- Every number points to its evidence (run directory, summary file, commit).
- Pilot/smoke numbers are **not** paper results; protocol runs start only after
  `docs/EXPERIMENT_PROTOCOL.md` is frozen.

Raw run directories (`results/runs/`) are git-ignored; summaries in `results/summary/`
are committed.

---

## 2026-10-09 — Schemathesis first contact (booking example)
- `st run --max-examples 50 --seed 42` on Schemathesis' `examples/booking` (FastAPI):
  384 generated cases, 1 failure (`POST /bookings` → 500 for `room_type: ""`, a
  `KeyError` in the price lookup), `GET /bookings/{booking_id}` always 404 (no valid ids).
- Observation: schema-only random generation does not reach semantically valid inputs or
  existing resources. This is the gap an ABC + LLM method could address.

## 2026-10-19 — Measurement infrastructure, first smoke
- Recording proxy + coverage.py + metric layer. Tools: Schemathesis (application),
  Hypothesis suite generated from OpenAPI (library).
- Booking, 20 s budget, seeds 42–44: both tools reach 1/3 operation success coverage;
  the KeyError is found and located (`KeyError @ app.py:46`).
- **Finding (fairness): Schemathesis keeps a crash cache** (`.schemathesis/`) in its
  working directory and replays cached crashes in later runs, so seeds were not
  independent. Fix: each run uses its own `tool/` directory as working directory.
- **Decision (fairness):** Hypothesis shrinking disabled, as Schemathesis runs with
  `--no-shrink` (its benchmarking guide). Budget goes to exploration in both.

## 2026-10-20 — EvoMaster 6.2.0 (black-box, Python output)
- **Finding:** EvoMaster crashed against uvicorn directly: uvicorn closes the connection
  after a 500, EvoMaster's pooled HTTP client fails on the reset. Through the proxy the
  tool-facing connection stays open, so the crash disappears. Documented as transport
  normalisation applied to all tools.
- EvoMaster tests hard-code their base URL → the proxy port is fixed for a whole run.
- **Finding (oracles):** EvoMaster writes regression oracles (`assert status_code ==
  500`); its suite passes on the buggy service (pass rate 1.0) while the property-oracle
  tools fail on the same bug. Pass rate is not comparable across tools.
- **Correction:** `--force` reruns kept the old run directory; the proxy appended to the
  old `traffic.jsonl` and Schemathesis reused its old cache. HTTP-call and failure counts
  reported in the chat on 2026-10-19/20 (794, 66, 1212) were inflated; coverage was not
  affected. Fixed (run directory removed first; proxy log truncated per session),
  smoke rerun from scratch.
- Clean smoke (`results/summary/smoke-booking.md`, 20 s, seeds 42–44):

  | | Schemathesis | Hypothesis | EvoMaster |
  |---|---|---|---|
  | operation success coverage | 1/3 | 1/3 | 1/3 |
  | line / branch coverage | 0.837 / 0.667 | 0.814 / 0.500 | 0.837 / 0.667 |
  | unique failures | 1 | 1 | 1 |
  | HTTP calls (median) | 391 | 33 | 458 |
  | suite pass rate | – | 0.667 | 1.0 |

  None of the tools gets `POST /bookings` to succeed: valid `room_type` values are not
  in the schema.

## 2026-10-21 — Representation, JVM route, benchmark decision
- Method-neutral representation (input positions, operation templates, URI-based
  resource dependencies). Owner decision: no evolutionary vocabulary (genes/chromosomes)
  in it; ABC maps positions to its own dimensions.
- Structural characteristics (Swagger 2.0 documents of WFD v4.3.0, `restgen spec inspect`):

  | service | operations | scalar positions | max depth | dependencies | unresolvable |
  |---|---|---|---|---|---|
  | catwatch | 23 | 81 | 5 | 0 | 0 |
  | features-service | 18 | 35 | 2 | 24 | 1 |
  | proxyprint | 115 | 173 | 3 | 39 | 32 |
  | rest-news | 7 | 19 | 2 | 3 | 0 |
  | scout-api | 49 | 504 | 5 | 23 | 0 |

  features-service needed a third creator pattern (`POST` on the element, client-chosen
  name); its remaining unresolvable dependency is created by an "action" endpoint
  (`POST .../constraints/excludes` → `/constraints/{id}`), which URIs cannot reveal.
  proxyprint puts verbs in URIs (`/consumer/requests/cancel/{id}`), hence 32.
- JVM route: JDK 8u504 + Maven 3.9.16 (pinned, checksum-verified), five services built.
  features-service, catwatch, rest-news, scout-api start (4.4–11.9 s) and are measured
  with JaCoCo on their own classes; proxyprint fails at startup (needs a writable
  documents directory). JaCoCo cannot analyse Spring Boot fat jars directly ("Can't add
  different class with same name"), so own-package classes are extracted first.
- A few manual requests on features-service: `GET /products/{missing}` → 500 instead of
  404, the fault pattern of the EvoMaster paper's Figure 3.
- **Owner decision:** the main benchmark is Python services; the JVM route stays as an
  optional, unpursued path.

## 2026-10-21 — First Python benchmark service: age-of-empires-II-api (WAFP)
- Setup: app cloned at WAFP's revision `6bd9f299…`, WAFP's frozen requirements on
  **Python 3.9.25** (WAFP: 3.7, which uv no longer provides; installed project-locally in
  `.tools/python`), **uWSGI skipped** (does not compile with current toolchains) and the
  app served by `flask run` instead of uWSGI + nginx. OpenAPI = the document the app
  serves (`/apispec.json`), not WAFP's hand-linked variant (it would inform only
  Schemathesis).
- **Finding (measurement bug):** flasgger serves a *hybrid* document with both
  `"swagger": "3.0"` and `"openapi": "3.0.0"`, `servers` and `definitions`. restgen
  treated it as Swagger 2.0, looked for `basePath`, found none, and matched no request to
  an operation: every tool showed 0/8 operation success although the traffic had 200s.
  Fixed: an `openapi` key means OpenAPI 3; `servers` first, then `basePath`.
- **Finding (tool configuration bug):** Schemathesis' `--url` replaces the document's
  `servers`, so it called `/technologies` instead of `/api/v1/technologies` (all 404);
  the Hypothesis suite had the same symptom through the wrong base path. Fixed: the runner
  passes the API base path to tools whose base-URL option overrides the document.
- Pilot after the fixes (20 s, seed 42, one run each; `results/runs/pilot/`, not paper
  data):

  | | Schemathesis | Hypothesis | EvoMaster |
  |---|---|---|---|
  | operations succeeded | 8/8 | 4/8 | 8/8 |
  | line / branch coverage | 0.819 / 0.833 | 0.784 / 0.611 | 0.819 / 0.833 |
  | unique failures | 0 | 0 | 0 |
  | HTTP calls | 304 | 124 | 162 |
  | success-coverage AUC (20 s) | 0.918 | 0.462 | 0.876 |

- Lesson: every new service gets a pilot whose traffic is inspected by hand before its
  numbers are trusted; a run where all tools score 0 is a measurement suspect first.

## 2026-10-22 — Hypothesis learning examples; lint scope bug
- `example/hypothesis/`: six runnable examples (properties, strategies, shrinking,
  stateful machines, `target()`, a real HTTP API from its OpenAPI document). All planted
  bugs are found and shrunk: `[0, 0]`; `price(31, "suite")`; a 4-step create/create/
  delete/create sequence; `days=0`; `room_type=""` (the same minimal input Schemathesis
  found on 2026-10-09).
- **Targeting illustration** (`example/hypothesis/compare_targeting.py`, not paper data):
  a bug confined to `4990 <= nights*guests <= 5000`, 300 inputs, 20 seeds: found in
  3/20 seeds without `target()`, 14/20 with it. A score-guided search clearly beats blind
  generation on narrow regions; this is the role ABC is meant to play, with a stronger
  search than Hypothesis's hill climbing.
- **Finding (repository hygiene):** ruff's `extend-exclude = ["benchmark", "hypothesis", ...]`
  matched those names at any depth, so `src/restgen/benchmark/` had never been linted
  (mypy did check it) and `example/hypothesis/` was skipped. Patterns are now anchored
  (`./benchmark`, ...); the newly linted code needed one line-length fix.
- The pilot run of 2026-10-21 (booking + restler-demo, 3 tools × 3 seeds) was interrupted
  by the end of the session; to be rerun.
