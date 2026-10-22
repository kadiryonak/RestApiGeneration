"""4. Stateful testing: generate whole SEQUENCES of operations, not single inputs.

A REST API is a state machine: POST creates, GET reads, DELETE removes. Bugs often need a
particular sequence (create -> delete -> read). Hypothesis's RuleBasedStateMachine
generates random sequences of "rules" (operations) and checks invariants after each step.
Schemathesis' stateful phase is built on this.

Run:  example/.venv/bin/pytest example/hypothesis/test_04_stateful.py -v
It FAILS on purpose: the printed steps are the shortest sequence that breaks the store.
"""

from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, invariant, rule


class BookingStore:
    """In-memory stand-in for a booking API, with a bug in delete."""

    def __init__(self) -> None:
        self.bookings: dict[int, str] = {}
        self.next_id = 1

    def create(self, guest: str) -> int:  # POST /bookings
        booking_id = self.next_id
        self.next_id += 1
        self.bookings[booking_id] = guest
        return booking_id

    def get(self, booking_id: int) -> str | None:  # GET /bookings/{id}
        return self.bookings.get(booking_id)

    def delete(self, booking_id: int) -> None:  # DELETE /bookings/{id}
        self.bookings.pop(booking_id, None)
        if len(self.bookings) == 1:
            self.next_id -= 1  # BUG: ids get reused when exactly one booking is left


class BookingMachine(RuleBasedStateMachine):
    # A Bundle holds values produced by earlier steps (the created ids), so later steps
    # can use them: this is how dependencies such as "GET needs an existing id" are made.
    ids = Bundle("ids")

    def __init__(self) -> None:
        super().__init__()
        self.store = BookingStore()
        self.model: dict[int, str] = {}  # the expected state (a simple model)

    @rule(target=ids, guest=st.text(min_size=1, max_size=5))
    def create(self, guest: str) -> int:
        booking_id = self.store.create(guest)
        assert booking_id not in self.model, "a new booking reused an existing id"
        self.model[booking_id] = guest
        return booking_id

    @rule(booking_id=ids)
    def read(self, booking_id: int) -> None:
        assert self.store.get(booking_id) == self.model.get(booking_id)

    @rule(booking_id=ids)
    def delete(self, booking_id: int) -> None:
        self.store.delete(booking_id)
        self.model.pop(booking_id, None)

    @invariant()
    def same_number_of_bookings(self) -> None:
        assert len(self.store.bookings) == len(self.model)


TestBookingMachine = BookingMachine.TestCase  # pytest collects this
