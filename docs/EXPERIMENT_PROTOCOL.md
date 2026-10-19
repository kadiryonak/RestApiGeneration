# Experiment protocol

**Status: not frozen.** Fill this in during phase 3 of `RESEARCH_PLAN.md`, date
it, and commit it **before any real run**. After that, conditions do not change
once results have been seen; every change goes into the change log below with
its date, reason and the runs it affects (which are then rerun).

## Open questions to settle before freezing
- **Budget parity.** Schemathesis is clock-bounded (`--max-time`); the Hypothesis suite is
  example-bounded (`max_examples` per operation). Choose one primary budget (wall time,
  HTTP calls or LLM cost incl. retries/repairs) and report the others (analysis §7.3).
- Repetitions: pilot first to measure variance and cost, then 10–30 per configuration
  (Schemathesis guide: at least 5, median, Mann-Whitney U + A12).
- Service roles (development / validation / evaluation) per service (analysis §6.2).
- Operations excluded from scope (e.g. logout, admin reset) and why.
- Success criterion for C_success (default 2xx) per service, if different.
- Equal information for every tool: black-box (OpenAPI + credentials + responses) as the
  main line; white-box (source, coverage feedback) only as an extra experiment.

## Order of experiments
_TBD_

## Fixed conditions
_TBD — benchmark (services, versions), method set, machine, LLM(s) and decoding
parameters, ABC parameters (SN, limit, MCN / evaluation budget), time and USD
budgets per run, seeds._

## Configurations (ablations / baselines)
| Config | Override |
|---|---|
| full | – |

## Statistics
_TBD — unit of analysis, number of repetitions per configuration, tests
(e.g. Wilcoxon signed-rank + Holm, Vargha–Delaney Â12; Friedman for >2
groups), how failures are counted._

## Commands
_TBD_

## Change log
_(empty until the protocol is frozen)_
