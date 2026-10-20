# pilot-python

Reference group: **schemathesis**. Cells: median [Q1, Q3] (n runs). A12 > 0.5 means the group's values are larger than the reference's; p is Holm-corrected over all comparisons of that metric.

## age-of-empires-2-api (real)

| Metric | schemathesis | hypothesis | evomaster |
|---|---|---|---|
| operation_success_coverage | 1 [1, 1] (3) | 0.5 [0.5, 0.5] (3)<br>A12=0.00 (large), p=0.0937 | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 |
| operation_attempt_coverage | 1 [1, 1] (3) | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 |
| line_coverage | 0.8192 [0.8105, 0.8192] (3) | 0.7843 [0.7843, 0.7843] (3)<br>A12=0.00 (large), p=0.119 | 0.8192 [0.8192, 0.8192] (3)<br>A12=0.67 (medium), p=0.505 |
| branch_coverage | 0.8333 [0.8056, 0.8333] (3) | 0.6111 [0.6111, 0.6111] (3)<br>A12=0.00 (large), p=0.119 | 0.8333 [0.8333, 0.8333] (3)<br>A12=0.67 (medium), p=0.505 |
| unique_failures | 0 [0, 0] (3) | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 |
| unique_crash_locations | 0 [0, 0] (3) | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 |
| output_line_coverage | - | 0.7843 [0.7843, 0.7843] (3) | 0.8192 [0.8192, 0.8192] (3) |
| line_retention | - | 1 [1, 1] (3) | 1 [1, 1] (3) |
| pass_rate | - | 1 [1, 1] (3) | 1 [1, 1] (3) |
| problem_rate | - | 0 [0, 0] (3) | 0 [0, 0] (3) |
| status_code_coverage | 1 [0.9583, 1] (3) | 0.6667 [0.6667, 0.6667] (3)<br>A12=0.00 (large), p=0.119 | 1 [1, 1] (3)<br>A12=0.67 (medium), p=0.505 |
| parameter_coverage | 1 [1, 1] (3) | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 |
| response_property_coverage | 0.8824 [0.8787, 0.8824] (3) | 0.5074 [0.5074, 0.5074] (3)<br>A12=0.00 (large), p=0.119 | 0.9118 [0.9081, 0.9265] (3)<br>A12=1.00 (large), p=0.119 |
| test_coverage_level | 2 [2, 2] (3) | 2 [2, 2] (3)<br>A12=0.50 (negligible), p=1 | 2 [2, 2] (3)<br>A12=0.50 (negligible), p=1 |
| operations_with_500 | 0 [0, 0] (3) | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 |
| unique_failure_points | 0 [0, 0] (3) | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 |
| success_coverage_auc | 0.9154 [0.9144, 0.9167] (3) | 0.4618 [0.4613, 0.462] (3)<br>A12=0.00 (large), p=0.2 | 0.858 [0.8269, 0.8624] (3)<br>A12=0.00 (large), p=0.2 |
| http_calls | 291 [291, 295] (3) | 124 [124, 124] (3)<br>A12=0.00 (large), p=0.119 | 168 [163, 173] (3)<br>A12=0.00 (large), p=0.119 |
| llm_calls | 0 [0, 0] (3) | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 |
| usd | 0 [0, 0] (3) | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 |
| wall_seconds | 20.52 [20.52, 20.54] (3) | 3.274 [3.226, 3.298] (3)<br>A12=0.00 (large), p=0.2 | 24.68 [24.43, 24.88] (3)<br>A12=1.00 (large), p=0.2 |

## booking (artificial)

| Metric | schemathesis | hypothesis | evomaster |
|---|---|---|---|
| operation_success_coverage | 0.3333 [0.3333, 0.3333] (2) | - | - |
| operation_attempt_coverage | 1 [1, 1] (2) | - | - |
| line_coverage | 0.8372 [0.8372, 0.8372] (2) | - | - |
| branch_coverage | 0.6667 [0.6667, 0.6667] (2) | - | - |
| unique_failures | 1 [1, 1] (2) | - | - |
| unique_crash_locations | 1 [1, 1] (2) | - | - |
| status_code_coverage | 0.5714 [0.5714, 0.5714] (2) | - | - |
| parameter_coverage | 1 [1, 1] (2) | - | - |
| response_property_coverage | 0.2308 [0.2308, 0.2308] (2) | - | - |
| test_coverage_level | 3 [3, 3] (2) | - | - |
| operations_with_500 | 1 [1, 1] (2) | - | - |
| unique_failure_points | 1 [1, 1] (2) | - | - |
| success_coverage_auc | 0.2841 [0.284, 0.2841] (2) | - | - |
| time_to_first_failure | 1.575 [1.552, 1.599] (2) | - | - |
| http_calls | 381.5 [380.2, 382.8] (2) | - | - |
| llm_calls | 0 [0, 0] (2) | - | - |
| usd | 0 [0, 0] (2) | - | - |
| wall_seconds | 20.55 [20.54, 20.56] (2) | - | - |

## Project-equal mean of per-service medians (real, 1 service(s))

| Metric | schemathesis | hypothesis | evomaster |
|---|---|---|---|
| operation_success_coverage | 1 | 0.5 | 1 |
| operation_attempt_coverage | 1 | 1 | 1 |
| line_coverage | 0.8192 | 0.7843 | 0.8192 |
| branch_coverage | 0.8333 | 0.6111 | 0.8333 |
| unique_failures | 0 | 0 | 0 |
| unique_crash_locations | 0 | 0 | 0 |
| output_line_coverage | - | 0.7843 | 0.8192 |
| line_retention | - | 1 | 1 |
| pass_rate | - | 1 | 1 |
| problem_rate | - | 0 | 0 |
| status_code_coverage | 1 | 0.6667 | 1 |
| parameter_coverage | 1 | 1 | 1 |
| response_property_coverage | 0.8824 | 0.5074 | 0.9118 |
| test_coverage_level | 2 | 2 | 2 |
| operations_with_500 | 0 | 0 | 0 |
| unique_failure_points | 0 | 0 | 0 |
| success_coverage_auc | 0.9154 | 0.4618 | 0.858 |
| http_calls | 291 | 124 | 168 |
| llm_calls | 0 | 0 | 0 |
| usd | 0 | 0 | 0 |
| wall_seconds | 20.52 | 3.274 | 24.68 |

## Project-equal mean of per-service medians (artificial, 1 service(s))

| Metric | schemathesis | hypothesis | evomaster |
|---|---|---|---|
| operation_success_coverage | 0.3333 | - | - |
| operation_attempt_coverage | 1 | - | - |
| line_coverage | 0.8372 | - | - |
| branch_coverage | 0.6667 | - | - |
| unique_failures | 1 | - | - |
| unique_crash_locations | 1 | - | - |
| status_code_coverage | 0.5714 | - | - |
| parameter_coverage | 1 | - | - |
| response_property_coverage | 0.2308 | - | - |
| test_coverage_level | 3 | - | - |
| operations_with_500 | 1 | - | - |
| unique_failure_points | 1 | - | - |
| success_coverage_auc | 0.2841 | - | - |
| time_to_first_failure | 1.575 | - | - |
| http_calls | 381.5 | - | - |
| llm_calls | 0 | - | - |
| usd | 0 | - | - |
| wall_seconds | 20.55 | - | - |

## Ranking over services (Friedman test on per-service medians)

| Metric | p | mean rank schemathesis | mean rank hypothesis | mean rank evomaster |
|---|---|---|---|---|

