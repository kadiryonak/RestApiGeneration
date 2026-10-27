"""A test case: an ordered sequence of HTTP actions run against one fresh service.

Order matters: an action may use what an earlier one returned (:class:`ResponseRef`),
which is how a test reaches states a single request cannot (create a user, then order
for it). :meth:`TestCase.validate` checks that every reference points backwards.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from restgen.core.representation.action import HttpAction, HttpRequest


@dataclass
class TestCase:
    __test__ = False  # not a pytest test class

    actions: list[HttpAction] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.actions)

    def validate(self) -> None:
        """Raise ``ValueError`` if an action refers to itself or to a later action."""
        for index, action in enumerate(self.actions):
            for ref in action.references():
                if not 0 <= ref.action < index:
                    raise ValueError(
                        f"action {index} ({action.operation.key}) refers to action "
                        f"{ref.action}; only actions 0..{index - 1} have run before it"
                    )

    def request(self, index: int, responses: Sequence[Any]) -> HttpRequest:
        """The request of action ``index``, given the parsed response bodies of actions
        ``0 .. index-1``."""
        return self.actions[index].to_request(responses[:index])

    def copy(self) -> TestCase:
        return TestCase([action.copy() for action in self.actions])

    def describe(self) -> list[dict[str, Any]]:
        return [action.describe() for action in self.actions]
