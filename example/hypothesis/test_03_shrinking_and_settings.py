"""3. Shrinking, reproducibility and settings.

Run:  example/.venv/bin/pytest example/hypothesis/test_03_shrinking_and_settings.py -v \
          --hypothesis-show-statistics

* Shrinking: after a failure Hypothesis simplifies the input (shorter lists, smaller
  numbers, shorter strings) as long as the test still fails, so you read the *simplest*
  failing case, not a random monster.
* @seed: the same seed gives the same inputs, so a run can be repeated exactly.
* settings: max_examples (how many inputs), deadline (time per example), phases (e.g.
  turn shrinking off, as restgen's baseline does so the budget goes to exploration).
"""

from hypothesis import Phase, given, seed, settings
from hypothesis import strategies as st


def price(nights: int, room_type: str) -> float:
    prices = {"standard": 99.99, "deluxe": 149.99, "suite": 299.99}
    total = prices[room_type] * nights
    if nights > 30 and room_type == "suite":
        total = total * -1  # a hidden bug in a rare branch
    return total


# FAILS on purpose. Hypothesis has to find nights > 30 AND room_type == "suite". The
# printed falsifying example is shrunk to the smallest such case: nights=31, "suite".
@given(st.integers(min_value=1, max_value=365), st.sampled_from(["standard", "deluxe", "suite"]))
def test_price_is_never_negative(nights: int, room_type: str) -> None:
    assert price(nights, room_type) >= 0


# Same seed -> same sequence of generated inputs: a failing run can be replayed exactly.
@seed(42)
@settings(max_examples=50, phases=[Phase.generate])  # no shrinking, generation only
@given(st.lists(st.integers(), max_size=5))
def test_seeded_run(values: list[int]) -> None:
    assert len(values) <= 5
