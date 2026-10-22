"""2. Strategies: describing the data, from simple values to whole JSON request bodies.

Run:  example/.venv/bin/pytest example/hypothesis/test_02_strategies.py -v -s
`-s` shows the printed samples, so you can see what Hypothesis generates.
"""

from datetime import date
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis_jsonschema import from_schema

# -- building blocks ------------------------------------------------------------------
small_ints = st.integers(min_value=1, max_value=365)  # bounds = documented constraints
names = st.text(min_size=2, max_size=100)  # minLength / maxLength
room_types = st.sampled_from(["standard", "deluxe", "suite"])  # an enum
emails = st.from_regex(r"[a-z]{3,8}@example\.org", fullmatch=True)  # a pattern
stays = st.dates(min_value=date(2026, 1, 1), max_value=date(2026, 12, 31))

# -- combining them: map, filter, builds, fixed_dictionaries ----------------------------
even = st.integers().map(lambda n: n * 2)  # transform values
non_empty_names = names.filter(lambda s: s.strip() != "")  # reject some values
booking = st.fixed_dictionaries(  # a JSON object with required keys...
    {"guest_name": non_empty_names, "room_type": room_types, "nights": small_ints},
    optional={"email": emails},  # ...and optional ones
)


@settings(max_examples=5)
@given(booking)
def test_show_generated_bookings(body: dict[str, Any]) -> None:
    print(body)  # see what Hypothesis produces
    assert 1 <= body["nights"] <= 365


# -- @st.composite: values that depend on each other -----------------------------------
@st.composite
def date_ranges(draw: st.DrawFn) -> tuple[date, date]:
    start = draw(stays)
    length = draw(st.integers(min_value=1, max_value=30))
    end = date.fromordinal(start.toordinal() + length)
    return start, end


@given(date_ranges())
def test_check_out_after_check_in(dates: tuple[date, date]) -> None:
    check_in, check_out = dates
    assert check_out > check_in


# -- straight from a JSON Schema: what restgen's Hypothesis baseline does --------------
BOOKING_SCHEMA = {  # this is the shape an OpenAPI document gives you
    "type": "object",
    "required": ["guest_name", "room_type", "nights"],
    "properties": {
        "guest_name": {"type": "string", "minLength": 2, "maxLength": 100},
        "room_type": {"type": "string"},  # the schema does NOT say which values are valid
        "nights": {"type": "integer", "exclusiveMinimum": 0, "maximum": 365},
    },
}


@settings(max_examples=5)
@given(from_schema(BOOKING_SCHEMA))
def test_bodies_from_json_schema(body: dict[str, Any]) -> None:
    print(body)  # room_type is random text: "standard"/"deluxe"/"suite" are never guessed
    assert 0 < body["nights"] <= 365
