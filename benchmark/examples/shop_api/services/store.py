"""In-memory storage: everything is lost when the server stops (a clean state per start)."""

USERS: dict[int, dict[str, object]] = {}
ORDERS: dict[int, dict[str, object]] = {}
COUNTERS = {"user": 0, "order": 0}


def next_id(kind: str) -> int:
    COUNTERS[kind] += 1
    return COUNTERS[kind]
