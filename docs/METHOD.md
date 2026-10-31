# DABC-HS method prototype

This document records the implementation mapping. It is not the experiment protocol;
no effectiveness claim follows from unit or smoke tests.

## Search

The implementation follows Sahin and Akay (2021):

- a food source is a structured `TestCase`, not a numeric vector;
- fitness remains a vector of target scores `h` in `[0, 1]` (`1` = covered,
  `1 / (1 + branch_distance)` = approached, `0` = not reached);
- each target has an archive population of at most `archive_size` candidates; a covered
  target retains only its shortest covering candidate;
- employed bees mutate current candidates; onlookers sample uncovered archive targets
  with the lowest selection counter;
- parent and offspring form one pool, then preference sorting protects the best candidate
  for every uncovered target before Pareto sorting and crowding reduction;
- the scout phase replaces candidates whose trial counter exceeds `limit`;
- Hyper-Scout cycles `size_factors` after `change_number` stagnant cycles and refreshes
  the active population after `reset_number` cycles without archive improvement;
- mutation count grows from `min_mutations` to `max_mutations` as the evaluation budget
  is consumed. Evaluation and wall-clock budgets are both hard stops.

All controls and the seed come from configuration/run context. Search code contains no
experiment parameter values.

## Resource construction and mutation

OpenAPI operations are grouped by resource. A dependency graph combines three kinds of
evidence:

1. URI/path evidence, such as `POST /users` before `GET /users/{user_id}`;
2. input-name and Python state evidence, such as `OrderCreate.user_id` and two handlers
   accessing the same repository/table/domain store;
3. fitness feedback when an ordered operation pair contributes new targets.

Lifecycle sampling recursively creates prerequisites and represents produced identifiers
as `ResponseRef` values. The reference is resolved from the real earlier response at
execution time, so generated suites do not hard-code database IDs. Mutations can change
values, append a complete lifecycle, delete a safe suffix, replace a lifecycle template,
or reorder independent resource actions. This is the Python counterpart of the 2021
resource/dependency approach; explicit Python repository/ORM hooks replace JVM SQL
instrumentation.

## Python white-box feedback

`PythonInstrumentation` is search-time guidance, not the source of reported coverage.
It records:

- reached source lines and exceptions with a trace hook;
- both outcomes of instrumented `if`/`while` conditions;
- numeric comparison distance and string equality edit distance;
- domain-store accesses exposed by repository or ORM hooks.

The AST transform preserves the original source file and gives every condition a stable
`file:line:column` identity. It is suitable for a Python service launched with the
instrumenting loader or for an in-process service. The existing coverage.py JSON remains
the authoritative post-run measurement, preventing search probes from being mistaken for
reported experimental results.

The current runner adapter executes DABC-HS through the recording proxy and therefore
uses response/status targets. Wiring the live white-box stream from a separately launched
benchmark process into the runner is a deployment task before white-box experiments; the
instrumentation and fitness interfaces are already isolated for that connection. Until
then, runner experiments must label this configuration black-box.

## Persistent output

The final target archive is de-duplicated and emitted as a pytest suite. Generated tests
resolve response references dynamically, take the base URL and headers from the runner,
and use the same no-5xx property oracle as the Hypothesis/Schemathesis line. The runner
collects the file and re-runs it on clean services through the same fixed-port recording
proxy used for every suite-producing comparison tool.
