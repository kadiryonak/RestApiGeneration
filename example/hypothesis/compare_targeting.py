"""Does targeting help? Same bug, same budget (300 inputs), 20 seeds, with and without
`target()`. Run:  cd example/hypothesis && ../.venv/bin/python compare_targeting.py

Result on 2026-10-22: without target the bug was found in 3/20 seeds, with target in
14/20. A guided search beats blind generation on a narrow region; ABC is a stronger
guided search than Hypothesis's hill climbing.
"""

from hypothesis import given, seed, settings, target
from hypothesis import strategies as st
from test_05_targeted import discount

SEEDS = 20
BUDGET = 300


def bug_found(use_target: bool, run_seed: int) -> bool:
    @seed(run_seed)
    @settings(max_examples=BUDGET, database=None, deadline=None)
    @given(st.integers(min_value=1, max_value=365), st.integers(min_value=1, max_value=50))
    def check(nights: int, guests: int) -> None:
        if use_target:
            target(-abs(nights * guests - 4995))
        discount(nights, guests)

    try:
        check()
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    for use_target in (False, True):
        hits = sum(bug_found(use_target, s) for s in range(SEEDS))
        print(f"target={'on ' if use_target else 'off'}: bug found in {hits}/{SEEDS} seeds")
