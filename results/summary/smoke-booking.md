# smoke-booking

Reference group: **schemathesis**. Cells: median [Q1, Q3] (n runs). A12 > 0.5 means the group's values are larger than the reference's; p is Holm-corrected over all comparisons of that metric.

## booking (artificial)

| Metric | schemathesis | hypothesis | evomaster |
|---|---|---|---|
| operation_success_coverage | 0.3333 [0.3333, 0.3333] (3) | 0.3333 [0.3333, 0.3333] (3)<br>A12=0.50 (negligible), p=1 | 0.3333 [0.3333, 0.3333] (3)<br>A12=0.50 (negligible), p=1 |
| operation_attempt_coverage | 1 [1, 1] (3) | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 |
| line_coverage | 0.8372 [0.8372, 0.8372] (3) | 0.814 [0.814, 0.814] (3)<br>A12=0.00 (large), p=0.0937 | 0.8372 [0.8372, 0.8372] (3)<br>A12=0.50 (negligible), p=1 |
| branch_coverage | 0.6667 [0.6667, 0.6667] (3) | 0.5 [0.5, 0.5] (3)<br>A12=0.00 (large), p=0.0937 | 0.6667 [0.6667, 0.6667] (3)<br>A12=0.50 (negligible), p=1 |
| unique_failures | 1 [1, 1] (3) | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 |
| unique_crash_locations | 1 [1, 1] (3) | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 |
| output_line_coverage | - | 0.814 [0.814, 0.814] (3) | 0.8372 [0.8372, 0.8372] (3) |
| line_retention | - | 1 [1, 1] (3) | 1 [1, 1] (3) |
| pass_rate | - | 0.6667 [0.6667, 0.6667] (3) | 1 [1, 1] (3) |
| success_coverage_auc | 0.2842 [0.2841, 0.2844] (3) | 0.3092 [0.3092, 0.3093] (3)<br>A12=1.00 (large), p=0.2 | 0.3033 [0.3012, 0.3048] (3)<br>A12=1.00 (large), p=0.2 |
| time_to_first_failure | 1.54 [1.527, 1.557] (3) | 1.107 [1.101, 1.112] (3)<br>A12=0.00 (large), p=0.2 | 1.908 [1.802, 2.016] (3)<br>A12=1.00 (large), p=0.2 |
| http_calls | 387 [387, 388] (3) | 33 [33, 33] (3)<br>A12=0.00 (large), p=0.119 | 456 [455, 461.5] (3)<br>A12=1.00 (large), p=0.119 |
| llm_calls | 0 [0, 0] (3) | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 |
| usd | 0 [0, 0] (3) | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 | 0 [0, 0] (3)<br>A12=0.50 (negligible), p=1 |
| wall_seconds | 20.53 [20.53, 20.55] (3) | 1.519 [1.518, 1.543] (3)<br>A12=0.00 (large), p=0.153 | 23.27 [23.2, 23.28] (3)<br>A12=1.00 (large), p=0.153 |

## Project-equal mean of per-service medians (artificial, 1 service(s))

| Metric | schemathesis | hypothesis | evomaster |
|---|---|---|---|
| operation_success_coverage | 0.3333 | 0.3333 | 0.3333 |
| operation_attempt_coverage | 1 | 1 | 1 |
| line_coverage | 0.8372 | 0.814 | 0.8372 |
| branch_coverage | 0.6667 | 0.5 | 0.6667 |
| unique_failures | 1 | 1 | 1 |
| unique_crash_locations | 1 | 1 | 1 |
| output_line_coverage | - | 0.814 | 0.8372 |
| line_retention | - | 1 | 1 |
| pass_rate | - | 0.6667 | 1 |
| success_coverage_auc | 0.2842 | 0.3092 | 0.3033 |
| time_to_first_failure | 1.54 | 1.107 | 1.908 |
| http_calls | 387 | 33 | 456 |
| llm_calls | 0 | 0 | 0 |
| usd | 0 | 0 | 0 |
| wall_seconds | 20.53 | 1.519 | 23.27 |

