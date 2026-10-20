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
| http_calls | 391 [389.5, 394] (3) | 33 [33, 33] (3)<br>A12=0.00 (large), p=0.127 | 458 [457, 461] (3)<br>A12=1.00 (large), p=0.127 |
| wall_seconds | 20.54 [20.52, 20.63] (3) | 1.418 [1.393, 1.419] (3)<br>A12=0.00 (large), p=0.2 | 22.56 [22.54, 22.75] (3)<br>A12=1.00 (large), p=0.2 |

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
| http_calls | 391 | 33 | 458 |
| wall_seconds | 20.54 | 1.418 | 22.56 |

