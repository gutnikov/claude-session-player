"""Per-session event buffer with replay support for SSE reconnection.

This module provides ring buffers that store the last N events per session,
enabling SSE clients to replay missed events after reconnection.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from uuid import uuid4

from claude_session_player.events import Event


@dataclass
class EventBuffer:
    """Per-session ring buffer storing the last N events.

    Supports replay for SSE reconnection via get_since() method.
    Events are stored with unique IDs for tracking.
    """

    max_size: int = 20
    _buffer: deque[tuple[str, Event]] = field(default_factory=deque, repr=False)
    _id_counter: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        """Initialize the deque with maxlen."""
        # Replace the default deque with one that has maxlen set
        self._buffer = deque(maxlen=self.max_size)

    def add(self, event: Event) -> str:
        """Add an event to the buffer and return its event ID.

        When the buffer is full, the oldest event is evicted.

        Args:
            event: The event to add.

        Returns:
            The unique event ID (e.g., "evt_001").
        """
        self._id_counter += 1
        event_id = f"evt_{self._id_counter:03d}"
        self._buffer.append((event_id, event))
        return event_id

    def get_since(self, event_id: str | None) -> list[tuple[str, Event]]:
        """Get all events after the given event ID.

        This is used for SSE replay when a client reconnects with Last-Event-ID.

        Args:
            event_id: The last event ID the client received.
                     If None or unknown, returns all buffered events.

        Returns:
            List of (event_id, event) tuples for events after the given ID.
            Returns all buffered events if event_id is None or not found.
        """
        if event_id is None:
            return list(self._buffer)

        # Find the index of the event_id in the buffer
        for i, (eid, _) in enumerate(self._buffer):
            if eid == event_id:
                # Return everything after this event
                return list(self._buffer)[i + 1 :]

        # event_id not found (evicted or unknown) - return all buffered events
        return list(self._buffer)

    def clear(self) -> None:
        """Clear all events from the buffer."""
        self._buffer.clear()
        # Reset counter when clearing for cleaner IDs
        self._id_counter = 0

    def __len__(self) -> int:
        """Return the number of events currently in the buffer."""
        return len(self._buffer)


@dataclass
class EventBufferManager:
    """Manager for per-session event buffers.

    Creates and manages EventBuffer instances for each session,
    providing a unified interface for event storage and retrieval.
    """

    max_size_per_session: int = 20
    _buffers: dict[str, EventBuffer] = field(default_factory=dict, repr=False)

    def get_buffer(self, session_id: str) -> EventBuffer:
        """Get or create an EventBuffer for the given session.

        Args:
            session_id: The session identifier.

        Returns:
            The EventBuffer for this session.
        """
        if session_id not in self._buffers:
            self._buffers[session_id] = EventBuffer(max_size=self.max_size_per_session)
        return self._buffers[session_id]

    def remove_buffer(self, session_id: str) -> None:
        """Remove the EventBuffer for the given session.

        Does nothing if the session doesn't have a buffer.

        Args:
            session_id: The session identifier.
        """
        self._buffers.pop(session_id, None)

    def add_event(self, session_id: str, event: Event) -> str:
        """Add an event to the specified session's buffer.

        Creates a buffer for the session if one doesn't exist.

        Args:
            session_id: The session identifier.
            event: The event to add.

        Returns:
            The unique event ID.
        """
        buffer = self.get_buffer(session_id)
        return buffer.add(event)

    def get_events_since(
        self, session_id: str, last_id: str | None
    ) -> list[tuple[str, Event]]:
        """Get events from a session's buffer after the given ID.

        Args:
            session_id: The session identifier.
            last_id: The last event ID the client received.

        Returns:
            List of (event_id, event) tuples for events after last_id.
            Returns empty list if session has no buffer.
        """
        if session_id not in self._buffers:
            return []
        return self._buffers[session_id].get_since(last_id)
