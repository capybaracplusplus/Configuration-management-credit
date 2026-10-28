"""Ordered in-memory transcript shared by snapshot and streaming readers."""

from threading import Condition, RLock
from typing import Any

POLL_SECONDS = 0.5


class Journal:
    """Record events under the same lock as session transitions."""

    def __init__(self) -> None:
        """Create an empty journal and its synchronization boundary."""
        self.condition = Condition(RLock())
        self.events: list[dict[str, Any]] = []

    def append(self, kind: str, **payload: Any) -> dict[str, Any]:
        """Append an event and wake every connected reader."""
        with self.condition:
            event = {"seq": len(self.events) + 1, "kind": kind, **payload}
            self.events.append(event)
            self.condition.notify_all()
            return event

    def after(self, cursor: int) -> list[dict[str, Any]]:
        """Return events after a cursor, waiting briefly if caught up."""
        with self.condition:
            if cursor >= len(self.events):
                self.condition.wait(POLL_SECONDS)
            return list(self.events[cursor:])
