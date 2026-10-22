"""5. Targeted property-based testing: steer the search with a score (Löscher & Sagonas,
ISSTA 2017; reading list no. 16).

Random generation rarely hits a narrow region of the input space. With
`hypothesis.target(score)` the test reports a number; Hypothesis then mutates inputs that
scored high to push the score further (simple hill climbing, hypothesis/internal/
conjecture/optimiser.py). This is the place where a stronger search such as ABC could
plug in: same idea, different optimiser.

Run:  example/.venv/bin/pytest example/hypothesis/test_05_targeted.py -v \
          --hypothesis-show-statistics
"""

from hypothesis import given, settings, target
from hypothesis import strategies as st


def discount(nights: int, guests: int) -> float:
    """Bug only when nights * guests is very close to 5000: a needle in a haystack."""
    stay = nights * guests
    if 4990 <= stay <= 5000:
        raise ValueError("overflow in the loyalty bonus")
    return 0.1 if stay > 100 else 0.0


@settings(max_examples=300)
@given(st.integers(min_value=1, max_value=365), st.integers(min_value=1, max_value=50))
def test_discount_targeted(nights: int, guests: int) -> None:
    # "the closer nights * guests gets to 5000, the better": a fitness value, like the
    # branch distance in EvoMaster or the nectar amount in ABC.
    target(-abs(nights * guests - 4995), label="closeness to 5000")
    discount(nights, guests)  # FAILS once the search reaches the narrow region
