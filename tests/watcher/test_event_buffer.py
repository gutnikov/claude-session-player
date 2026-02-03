"""Tests for the event buffer module."""

from __future__ import annotations

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    UpdateBlock,
)
from claude_session_player.watcher.event_buffer import EventBuffer, EventBufferManager


# --- Helper functions ---


def make_add_block_event(text: str = "test") -> AddBlock:
    """Create a simple AddBlock event for testing."""
    return AddBlock(
        block=Block(
            id=f"block_{text}",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text=text),
        )
    )


def make_update_block_event(block_id: str = "block_1", text: str = "updated") -> UpdateBlock:
    """Create a simple UpdateBlock event for testing."""
    return UpdateBlock(
        block_id=block_id,
        content=AssistantContent(text=text),
    )


# --- EventBuffer tests ---


class TestEventBufferCreation:
    """Tests for EventBuffer creation and initialization."""

    def test_default_max_size(self) -> None:
        """EventBuffer defaults to max_size of 20."""
        buffer = EventBuffer()
        assert buffer.max_size == 20

    def test_custom_max_size(self) -> None:
        """EventBuffer accepts custom max_size."""
        buffer = EventBuffer(max_size=10)
        assert buffer.max_size == 10

    def test_empty_on_creation(self) -> None:
        """EventBuffer is empty on creation."""
        buffer = EventBuffer()
        assert len(buffer) == 0


class TestEventBufferAdd:
    """Tests for EventBuffer.add() method."""

    def test_add_returns_event_id(self) -> None:
        """add() returns a unique event ID."""
        buffer = EventBuffer()
        event = make_add_block_event()
        event_id = buffer.add(event)
        assert event_id == "evt_001"

    def test_add_sequential_ids(self) -> None:
        """add() generates sequential event IDs."""
        buffer = EventBuffer()
        ids = [buffer.add(make_add_block_event(f"test_{i}")) for i in range(3)]
        assert ids == ["evt_001", "evt_002", "evt_003"]

    def test_add_increments_length(self) -> None:
        """add() increments buffer length."""
        buffer = EventBuffer()
        assert len(buffer) == 0
        buffer.add(make_add_block_event())
        assert len(buffer) == 1
        buffer.add(make_add_block_event())
        assert len(buffer) == 2

    def test_add_up_to_max_size(self) -> None:
        """Buffer stores events up to max_size."""
        buffer = EventBuffer(max_size=5)
        for i in range(5):
            buffer.add(make_add_block_event(f"test_{i}"))
        assert len(buffer) == 5


class TestEventBufferEviction:
    """Tests for EventBuffer eviction when exceeding max_size."""

    def test_evicts_oldest_when_full(self) -> None:
        """Oldest event is evicted when buffer exceeds max_size."""
        buffer = EventBuffer(max_size=3)
        buffer.add(make_add_block_event("first"))
        buffer.add(make_add_block_event("second"))
        buffer.add(make_add_block_event("third"))
        buffer.add(make_add_block_event("fourth"))

        assert len(buffer) == 3
        events = buffer.get_since(None)
        texts = [e[1].block.content.text for e in events]
        assert texts == ["second", "third", "fourth"]

    def test_continuous_eviction(self) -> None:
        """Continuous adds evict oldest events."""
        buffer = EventBuffer(max_size=2)
        for i in range(5):
            buffer.add(make_add_block_event(f"event_{i}"))

        assert len(buffer) == 2
        events = buffer.get_since(None)
        texts = [e[1].block.content.text for e in events]
        assert texts == ["event_3", "event_4"]

    def test_id_counter_continues_after_eviction(self) -> None:
        """Event ID counter continues incrementing after eviction."""
        buffer = EventBuffer(max_size=2)
        buffer.add(make_add_block_event("a"))  # evt_001
        buffer.add(make_add_block_event("b"))  # evt_002
        event_id = buffer.add(make_add_block_event("c"))  # evt_003

        assert event_id == "evt_003"
        events = buffer.get_since(None)
        assert events[0][0] == "evt_002"
        assert events[1][0] == "evt_003"


class TestEventBufferGetSince:
    """Tests for EventBuffer.get_since() method."""

    def test_get_since_none_returns_all(self) -> None:
        """get_since(None) returns all buffered events."""
        buffer = EventBuffer()
        buffer.add(make_add_block_event("a"))
        buffer.add(make_add_block_event("b"))
        buffer.add(make_add_block_event("c"))

        events = buffer.get_since(None)
        assert len(events) == 3
        texts = [e[1].block.content.text for e in events]
        assert texts == ["a", "b", "c"]

    def test_get_since_valid_id_returns_subset(self) -> None:
        """get_since(valid_id) returns events after that ID."""
        buffer = EventBuffer()
        buffer.add(make_add_block_event("a"))  # evt_001
        buffer.add(make_add_block_event("b"))  # evt_002
        buffer.add(make_add_block_event("c"))  # evt_003

        events = buffer.get_since("evt_001")
        assert len(events) == 2
        texts = [e[1].block.content.text for e in events]
        assert texts == ["b", "c"]

    def test_get_since_last_id_returns_empty(self) -> None:
        """get_since(last_event_id) returns empty list."""
        buffer = EventBuffer()
        buffer.add(make_add_block_event("a"))  # evt_001
        last_id = buffer.add(make_add_block_event("b"))  # evt_002

        events = buffer.get_since(last_id)
        assert len(events) == 0

    def test_get_since_unknown_id_returns_all(self) -> None:
        """get_since(unknown_id) returns all buffered events."""
        buffer = EventBuffer()
        buffer.add(make_add_block_event("a"))
        buffer.add(make_add_block_event("b"))

        events = buffer.get_since("evt_999")
        assert len(events) == 2
        texts = [e[1].block.content.text for e in events]
        assert texts == ["a", "b"]

    def test_get_since_evicted_id_returns_all(self) -> None:
        """get_since(evicted_id) returns all buffered events."""
        buffer = EventBuffer(max_size=2)
        buffer.add(make_add_block_event("a"))  # evt_001, will be evicted
        buffer.add(make_add_block_event("b"))  # evt_002
        buffer.add(make_add_block_event("c"))  # evt_003

        # evt_001 was evicted
        events = buffer.get_since("evt_001")
        assert len(events) == 2
        texts = [e[1].block.content.text for e in events]
        assert texts == ["b", "c"]

    def test_get_since_middle_id(self) -> None:
        """get_since(middle_id) returns events after that ID."""
        buffer = EventBuffer()
        buffer.add(make_add_block_event("a"))  # evt_001
        buffer.add(make_add_block_event("b"))  # evt_002
        buffer.add(make_add_block_event("c"))  # evt_003
        buffer.add(make_add_block_event("d"))  # evt_004

        events = buffer.get_since("evt_002")
        assert len(events) == 2
        texts = [e[1].block.content.text for e in events]
        assert texts == ["c", "d"]

    def test_get_since_empty_buffer(self) -> None:
        """get_since() on empty buffer returns empty list."""
        buffer = EventBuffer()
        events = buffer.get_since(None)
        assert events == []

        events = buffer.get_since("evt_001")
        assert events == []


class TestEventBufferClear:
    """Tests for EventBuffer.clear() method."""

    def test_clear_empties_buffer(self) -> None:
        """clear() removes all events from buffer."""
        buffer = EventBuffer()
        buffer.add(make_add_block_event("a"))
        buffer.add(make_add_block_event("b"))
        assert len(buffer) == 2

        buffer.clear()
        assert len(buffer) == 0
        assert buffer.get_since(None) == []

    def test_clear_resets_id_counter(self) -> None:
        """clear() resets the ID counter."""
        buffer = EventBuffer()
        buffer.add(make_add_block_event("a"))  # evt_001
        buffer.add(make_add_block_event("b"))  # evt_002
        buffer.clear()

        event_id = buffer.add(make_add_block_event("c"))
        assert event_id == "evt_001"


class TestEventBufferEventTypes:
    """Tests for different event types in the buffer."""

    def test_stores_add_block_events(self) -> None:
        """Buffer correctly stores AddBlock events."""
        buffer = EventBuffer()
        event = make_add_block_event("test")
        buffer.add(event)

        events = buffer.get_since(None)
        assert len(events) == 1
        assert isinstance(events[0][1], AddBlock)

    def test_stores_update_block_events(self) -> None:
        """Buffer correctly stores UpdateBlock events."""
        buffer = EventBuffer()
        event = make_update_block_event()
        buffer.add(event)

        events = buffer.get_since(None)
        assert len(events) == 1
        assert isinstance(events[0][1], UpdateBlock)

    def test_stores_clear_all_events(self) -> None:
        """Buffer correctly stores ClearAll events."""
        buffer = EventBuffer()
        event = ClearAll()
        buffer.add(event)

        events = buffer.get_since(None)
        assert len(events) == 1
        assert isinstance(events[0][1], ClearAll)

    def test_stores_mixed_event_types(self) -> None:
        """Buffer correctly stores mixed event types."""
        buffer = EventBuffer()
        buffer.add(make_add_block_event("a"))
        buffer.add(make_update_block_event())
        buffer.add(ClearAll())

        events = buffer.get_since(None)
        assert len(events) == 3
        assert isinstance(events[0][1], AddBlock)
        assert isinstance(events[1][1], UpdateBlock)
        assert isinstance(events[2][1], ClearAll)


# --- EventBufferManager tests ---


class TestEventBufferManagerCreation:
    """Tests for EventBufferManager creation."""

    def test_default_max_size(self) -> None:
        """EventBufferManager defaults to max_size_per_session of 20."""
        manager = EventBufferManager()
        assert manager.max_size_per_session == 20

    def test_custom_max_size(self) -> None:
        """EventBufferManager accepts custom max_size_per_session."""
        manager = EventBufferManager(max_size_per_session=10)
        assert manager.max_size_per_session == 10


class TestEventBufferManagerGetBuffer:
    """Tests for EventBufferManager.get_buffer() method."""

    def test_creates_buffer_on_first_access(self) -> None:
        """get_buffer() creates new buffer if session doesn't exist."""
        manager = EventBufferManager()
        buffer = manager.get_buffer("session_1")

        assert isinstance(buffer, EventBuffer)
        assert len(buffer) == 0

    def test_returns_same_buffer_on_subsequent_access(self) -> None:
        """get_buffer() returns the same buffer for the same session."""
        manager = EventBufferManager()
        buffer1 = manager.get_buffer("session_1")
        buffer1.add(make_add_block_event("test"))

        buffer2 = manager.get_buffer("session_1")
        assert buffer1 is buffer2
        assert len(buffer2) == 1

    def test_creates_separate_buffers_per_session(self) -> None:
        """get_buffer() creates separate buffers for different sessions."""
        manager = EventBufferManager()
        buffer1 = manager.get_buffer("session_1")
        buffer2 = manager.get_buffer("session_2")

        buffer1.add(make_add_block_event("test1"))

        assert buffer1 is not buffer2
        assert len(buffer1) == 1
        assert len(buffer2) == 0

    def test_buffer_uses_manager_max_size(self) -> None:
        """Created buffers use the manager's max_size_per_session."""
        manager = EventBufferManager(max_size_per_session=5)
        buffer = manager.get_buffer("session_1")

        assert buffer.max_size == 5


class TestEventBufferManagerRemoveBuffer:
    """Tests for EventBufferManager.remove_buffer() method."""

    def test_removes_existing_buffer(self) -> None:
        """remove_buffer() removes an existing buffer."""
        manager = EventBufferManager()
        buffer = manager.get_buffer("session_1")
        buffer.add(make_add_block_event("test"))

        manager.remove_buffer("session_1")

        # Getting buffer again creates a new empty one
        new_buffer = manager.get_buffer("session_1")
        assert len(new_buffer) == 0

    def test_remove_nonexistent_buffer_is_noop(self) -> None:
        """remove_buffer() does nothing for nonexistent session."""
        manager = EventBufferManager()
        # Should not raise
        manager.remove_buffer("nonexistent")

    def test_remove_cleans_up_session(self) -> None:
        """remove_buffer() cleans up the session completely."""
        manager = EventBufferManager()
        manager.get_buffer("session_1")
        manager.get_buffer("session_2")

        manager.remove_buffer("session_1")

        # session_2 should still exist
        events = manager.get_events_since("session_2", None)
        assert events == []

        # session_1 should be gone (get_events_since returns empty for nonexistent)
        events = manager.get_events_since("session_1", None)
        assert events == []


class TestEventBufferManagerAddEvent:
    """Tests for EventBufferManager.add_event() method."""

    def test_add_event_returns_id(self) -> None:
        """add_event() returns the event ID."""
        manager = EventBufferManager()
        event_id = manager.add_event("session_1", make_add_block_event("test"))

        assert event_id == "evt_001"

    def test_add_event_creates_buffer_if_needed(self) -> None:
        """add_event() creates buffer for session if it doesn't exist."""
        manager = EventBufferManager()
        manager.add_event("session_1", make_add_block_event("test"))

        events = manager.get_events_since("session_1", None)
        assert len(events) == 1

    def test_add_event_sequential_ids_per_session(self) -> None:
        """add_event() generates sequential IDs per session."""
        manager = EventBufferManager()
        id1 = manager.add_event("session_1", make_add_block_event("a"))
        id2 = manager.add_event("session_1", make_add_block_event("b"))
        id3 = manager.add_event("session_2", make_add_block_event("x"))

        assert id1 == "evt_001"
        assert id2 == "evt_002"
        assert id3 == "evt_001"  # Different session, starts at 001


class TestEventBufferManagerGetEventsSince:
    """Tests for EventBufferManager.get_events_since() method."""

    def test_returns_events_from_session(self) -> None:
        """get_events_since() returns events from the specified session."""
        manager = EventBufferManager()
        manager.add_event("session_1", make_add_block_event("a"))
        manager.add_event("session_1", make_add_block_event("b"))

        events = manager.get_events_since("session_1", None)
        assert len(events) == 2

    def test_returns_events_after_id(self) -> None:
        """get_events_since() returns events after the given ID."""
        manager = EventBufferManager()
        manager.add_event("session_1", make_add_block_event("a"))  # evt_001
        manager.add_event("session_1", make_add_block_event("b"))  # evt_002
        manager.add_event("session_1", make_add_block_event("c"))  # evt_003

        events = manager.get_events_since("session_1", "evt_001")
        assert len(events) == 2

    def test_returns_empty_for_nonexistent_session(self) -> None:
        """get_events_since() returns empty list for nonexistent session."""
        manager = EventBufferManager()
        events = manager.get_events_since("nonexistent", None)
        assert events == []

    def test_sessions_are_independent(self) -> None:
        """Events from different sessions don't interfere."""
        manager = EventBufferManager()
        manager.add_event("session_1", make_add_block_event("s1_a"))
        manager.add_event("session_1", make_add_block_event("s1_b"))
        manager.add_event("session_2", make_add_block_event("s2_a"))

        events1 = manager.get_events_since("session_1", None)
        events2 = manager.get_events_since("session_2", None)

        assert len(events1) == 2
        assert len(events2) == 1
        assert events1[0][1].block.content.text == "s1_a"
        assert events2[0][1].block.content.text == "s2_a"


class TestEventBufferManagerIntegration:
    """Integration tests for EventBufferManager."""

    def test_full_workflow(self) -> None:
        """Test a complete workflow: add, get, remove."""
        manager = EventBufferManager(max_size_per_session=3)

        # Add events to two sessions
        manager.add_event("session_1", make_add_block_event("s1_1"))
        manager.add_event("session_1", make_add_block_event("s1_2"))
        manager.add_event("session_2", make_add_block_event("s2_1"))

        # Verify events
        s1_events = manager.get_events_since("session_1", None)
        s2_events = manager.get_events_since("session_2", None)
        assert len(s1_events) == 2
        assert len(s2_events) == 1

        # Remove session_1
        manager.remove_buffer("session_1")

        # Verify session_1 is gone, session_2 remains
        s1_events = manager.get_events_since("session_1", None)
        s2_events = manager.get_events_since("session_2", None)
        assert len(s1_events) == 0
        assert len(s2_events) == 1

    def test_eviction_per_session(self) -> None:
        """Each session has independent eviction."""
        manager = EventBufferManager(max_size_per_session=2)

        # Add 3 events to session_1 (should evict first)
        manager.add_event("session_1", make_add_block_event("s1_1"))
        manager.add_event("session_1", make_add_block_event("s1_2"))
        manager.add_event("session_1", make_add_block_event("s1_3"))

        # Add 1 event to session_2
        manager.add_event("session_2", make_add_block_event("s2_1"))

        # session_1 should have only last 2
        s1_events = manager.get_events_since("session_1", None)
        assert len(s1_events) == 2
        texts = [e[1].block.content.text for e in s1_events]
        assert texts == ["s1_2", "s1_3"]

        # session_2 should have 1
        s2_events = manager.get_events_since("session_2", None)
        assert len(s2_events) == 1


class TestEventIdFormat:
    """Tests for event ID format and ordering."""

    def test_event_id_format(self) -> None:
        """Event IDs follow evt_NNN format."""
        buffer = EventBuffer()
        event_id = buffer.add(make_add_block_event("test"))
        assert event_id.startswith("evt_")
        assert event_id == "evt_001"

    def test_event_ids_are_ordered(self) -> None:
        """Event IDs are numerically ordered."""
        buffer = EventBuffer()
        ids = [buffer.add(make_add_block_event(f"e_{i}")) for i in range(5)]

        # IDs should be lexicographically ordered
        assert ids == sorted(ids)

    def test_event_id_padding(self) -> None:
        """Event IDs are zero-padded for ordering."""
        buffer = EventBuffer()
        for i in range(10):
            buffer.add(make_add_block_event(f"e_{i}"))

        events = buffer.get_since(None)
        ids = [e[0] for e in events]

        # Should be evt_001 through evt_010
        assert ids[0] == "evt_001"
        assert ids[9] == "evt_010"
