# smoke-booking

Reference group: **schemathesis**. Cells: median [Q1, Q3] (n runs). A12 > 0.5 means the group's values are larger than the reference's; p is Holm-corrected over all comparisons of that metric.

## booking (artificial)

| Metric | schemathesis | hypothesis |
|---|---|---|
| operation_success_coverage | 0.3333 [0.3333, 0.3333] (3) | 0.3333 [0.3333, 0.3333] (3)<br>A12=0.50 (negligible), p=1 |
| operation_attempt_coverage | 1 [1, 1] (3) | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 |
| line_coverage | 0.8372 [0.8372, 0.8372] (3) | 0.814 [0.814, 0.814] (3)<br>A12=0.00 (large), p=0.0469 |
| branch_coverage | 0.6667 [0.6667, 0.6667] (3) | 0.5 [0.5, 0.5] (3)<br>A12=0.00 (large), p=0.0469 |
| unique_failures | 1 [1, 1] (3) | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 |
| unique_crash_locations | 1 [1, 1] (3) | 1 [1, 1] (3)<br>A12=0.50 (negligible), p=1 |
| output_line_coverage | - | 0.814 [0.814, 0.814] (3) |
| line_retention | - | 1 [1, 1] (3) |
| pass_rate | - | 0.6667 [0.6667, 0.6667] (3) |
| http_calls | 794 [792.5, 988.5] (3) | 66 [66, 136] (3)<br>A12=0.00 (large), p=0.0765 |
| wall_seconds | 20.53 [20.53, 20.55] (3) | 0.719 [0.7175, 0.7675] (3)<br>A12=0.00 (large), p=0.1 |

## Project-equal mean of per-service medians (artificial, 1 service(s))

| Metric | schemathesis | hypothesis |
|---|---|---|
| operation_success_coverage | 0.3333 | 0.3333 |
| operation_attempt_coverage | 1 | 1 |
| line_coverage | 0.8372 | 0.814 |
| branch_coverage | 0.6667 | 0.5 |
| unique_failures | 1 | 1 |
| unique_crash_locations | 1 | 1 |
| output_line_coverage | - | 0.814 |
| line_retention | - | 1 |
| pass_rate | - | 0.6667 |
| http_calls | 794 | 66 |
| wall_seconds | 20.53 | 0.719 |

