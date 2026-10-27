# Examples

Small, runnable examples for learning the tools used in this project. They are not part
of restgen (not linted by CI's test run, not in the package).

## Hypothesis (`example/hypothesis/`)

```bash
uv venv --python 3.12 example/.venv
uv pip install --python example/.venv/bin/python -r example/requirements.txt
cd example/hypothesis
../.venv/bin/pytest -v --hypothesis-show-statistics          # all six
../.venv/bin/pytest -v test_01_basics.py                     # one by one
```

| File | Shows | Fails on purpose? |
|---|---|---|
| `test_01_basics.py` | `@given`, properties instead of examples, shrinking to `[0, 0]` | yes (buggy sort) |
| `test_02_strategies.py` | strategies, `map`/`filter`, `@composite`, JSON bodies, `from_schema` | no (`-s` prints samples) |
| `test_03_shrinking_and_settings.py` | shrinking of a rare bug, `@seed`, `max_examples`, phases | yes (negative price) |
| `test_04_stateful.py` | `RuleBasedStateMachine`: sequences of operations, `Bundle` for ids | yes (id reuse after delete) |
| `test_05_targeted.py` | `target()`: steering generation with a score (hill climbing) | yes (narrow bug region) |
| `test_06_rest_api.py` | a real HTTP API tested from its OpenAPI document | yes (two 500s) |

`compare_targeting.py` repeats the bug hunt of `test_05` over 20 seeds with the same budget
(300 inputs): without `target()` the bug was found in **3/20** seeds, with it in
**14/20** (2026-10-22). Guided search matters; that is the motivation for ABC.

## Representation (`example/representation/`)

From the Shop API's OpenAPI document to operation templates to a hand-built test case of
three actions (create an `ADMIN` user, read it back by the returned id, order two
laptops for it). Uses restgen itself, so it runs in the repository's `.venv`:

```bash
.venv/bin/python example/representation/demo_testcase.py              # print only
# with the Shop API running (see benchmark/examples/shop_api/README.md):
.venv/bin/python example/representation/demo_testcase.py --url http://127.0.0.1:8000
```
