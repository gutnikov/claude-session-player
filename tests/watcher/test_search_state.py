"""Tests for SearchStateManager and SearchState."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from claude_session_player.watcher.indexer import SessionInfo
from claude_session_player.watcher.search import SearchFilters
from claude_session_player.watcher.search_state import SearchState, SearchStateManager


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def make_session_info(session_id: str, summary: str | None = None) -> SessionInfo:
    """Create a SessionInfo for testing."""
    return SessionInfo(
        session_id=session_id,
        project_encoded="-Users-test-project",
        project_display_name="project",
        file_path=Path(f"/tmp/{session_id}.jsonl"),
        summary=summary,
        created_at=datetime.now(timezone.utc),
        modified_at=datetime.now(timezone.utc),
        size_bytes=1000,
        line_count=100,
        has_subagents=False,
    )


def make_search_state(
    num_results: int = 10,
    offset: int = 0,
    message_id: int | str = 12345,
    created_at: datetime | None = None,
) -> SearchState:
    """Create a SearchState for testing."""
    results = [make_session_info(f"session-{i}", f"Summary {i}") for i in range(num_results)]
    return SearchState(
        query="test query",
        filters=SearchFilters(),
        results=results,
        current_offset=offset,
        message_id=message_id,
        created_at=created_at or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# SearchState tests
# ---------------------------------------------------------------------------


class TestSearchStateGetPage:
    """Tests for SearchState.get_page()."""

    def test_get_first_page(self) -> None:
        """Get first page of results."""
        state = make_search_state(num_results=12, offset=0)
        page = state.get_page(limit=5)
        assert len(page) == 5
        assert page[0].session_id == "session-0"
        assert page[4].session_id == "session-4"

    def test_get_middle_page(self) -> None:
        """Get middle page of results."""
        state = make_search_state(num_results=12, offset=5)
        page = state.get_page(limit=5)
        assert len(page) == 5
        assert page[0].session_id == "session-5"
        assert page[4].session_id == "session-9"

    def test_get_last_page_partial(self) -> None:
        """Get last page with fewer than limit results."""
        state = make_search_state(num_results=12, offset=10)
        page = state.get_page(limit=5)
        assert len(page) == 2
        assert page[0].session_id == "session-10"
        assert page[1].session_id == "session-11"

    def test_get_page_empty_results(self) -> None:
        """Get page when offset is beyond results."""
        state = make_search_state(num_results=5, offset=10)
        page = state.get_page(limit=5)
        assert len(page) == 0

    def test_get_page_custom_limit(self) -> None:
        """Get page with custom limit."""
        state = make_search_state(num_results=10, offset=0)
        page = state.get_page(limit=3)
        assert len(page) == 3


class TestSearchStateSessionAtIndex:
    """Tests for SearchState.session_at_index()."""

    def test_session_at_valid_index(self) -> None:
        """Get session at valid page-relative index."""
        state = make_search_state(num_results=10, offset=5)
        session = state.session_at_index(0)
        assert session is not None
        assert session.session_id == "session-5"

    def test_session_at_index_middle(self) -> None:
        """Get session at middle of page."""
        state = make_search_state(num_results=10, offset=5)
        session = state.session_at_index(2)
        assert session is not None
        assert session.session_id == "session-7"

    def test_session_at_index_out_of_bounds(self) -> None:
        """Returns None for out of bounds index."""
        state = make_search_state(num_results=10, offset=8)
        # Only indices 0 and 1 are valid (sessions 8 and 9)
        session = state.session_at_index(5)
        assert session is None

    def test_session_at_negative_index(self) -> None:
        """Returns None for negative index."""
        state = make_search_state(num_results=10, offset=0)
        session = state.session_at_index(-1)
        assert session is None


class TestSearchStatePaginationHelpers:
    """Tests for SearchState pagination helpers."""

    def test_has_next_page_true(self) -> None:
        """has_next_page returns True when more results exist."""
        state = make_search_state(num_results=10, offset=0)
        assert state.has_next_page(limit=5) is True

    def test_has_next_page_false_exact(self) -> None:
        """has_next_page returns False at exact boundary."""
        state = make_search_state(num_results=10, offset=5)
        assert state.has_next_page(limit=5) is False

    def test_has_next_page_false_partial(self) -> None:
        """has_next_page returns False on partial last page."""
        state = make_search_state(num_results=8, offset=5)
        assert state.has_next_page(limit=5) is False

    def test_has_prev_page_true(self) -> None:
        """has_prev_page returns True when offset > 0."""
        state = make_search_state(num_results=10, offset=5)
        assert state.has_prev_page() is True

    def test_has_prev_page_false(self) -> None:
        """has_prev_page returns False on first page."""
        state = make_search_state(num_results=10, offset=0)
        assert state.has_prev_page() is False


# ---------------------------------------------------------------------------
# SearchStateManager tests
# ---------------------------------------------------------------------------


class TestSearchStateManagerSaveAndGet:
    """Tests for SearchStateManager save and get operations."""

    def test_save_and_retrieve_state(self) -> None:
        """Save state and retrieve it."""
        manager = SearchStateManager()
        state = make_search_state(num_results=5)
        chat_id = "telegram:123456789"

        manager.save(chat_id, state)
        retrieved = manager.get(chat_id)

        assert retrieved is not None
        assert retrieved.query == "test query"
        assert len(retrieved.results) == 5

    def test_get_nonexistent_state(self) -> None:
        """Get returns None for nonexistent chat_id."""
        manager = SearchStateManager()
        result = manager.get("telegram:nonexistent")
        assert result is None

    def test_new_search_replaces_old_state(self) -> None:
        """New search replaces previous state for the same chat."""
        manager = SearchStateManager()
        chat_id = "telegram:123456789"

        state1 = make_search_state(num_results=5)
        state1.query = "first query"
        manager.save(chat_id, state1)

        state2 = make_search_state(num_results=3)
        state2.query = "second query"
        manager.save(chat_id, state2)

        retrieved = manager.get(chat_id)
        assert retrieved is not None
        assert retrieved.query == "second query"
        assert len(retrieved.results) == 3


class TestSearchStateManagerTTL:
    """Tests for TTL expiration."""

    def test_state_expires_after_ttl(self) -> None:
        """State is not returned after TTL expires."""
        manager = SearchStateManager(ttl_seconds=60)
        chat_id = "telegram:123456789"

        # Create state with old created_at
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        state = make_search_state(created_at=old_time)

        manager._states[chat_id] = state  # Bypass save to set old timestamp

        result = manager.get(chat_id)
        assert result is None

    def test_state_not_expired_within_ttl(self) -> None:
        """State is returned within TTL."""
        manager = SearchStateManager(ttl_seconds=300)
        chat_id = "telegram:123456789"

        # Create state 60 seconds ago (within 300s TTL)
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=60)
        state = make_search_state(created_at=recent_time)

        manager._states[chat_id] = state

        result = manager.get(chat_id)
        assert result is not None

    def test_expired_states_cleaned_on_save(self) -> None:
        """Expired states from other chats are cleaned up on save."""
        manager = SearchStateManager(ttl_seconds=60)

        # Add an expired state
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        expired_state = make_search_state(created_at=old_time)
        manager._states["telegram:expired"] = expired_state

        # Save a new state (should trigger cleanup)
        new_state = make_search_state()
        manager.save("telegram:new", new_state)

        # Expired state should be gone
        assert "telegram:expired" not in manager._states
        # New state should exist
        assert "telegram:new" in manager._states


class TestSearchStateManagerUpdateOffset:
    """Tests for update_offset operation."""

    def test_update_offset_success(self) -> None:
        """Update offset successfully."""
        manager = SearchStateManager()
        chat_id = "telegram:123456789"

        state = make_search_state(num_results=10, offset=0)
        manager.save(chat_id, state)

        updated = manager.update_offset(chat_id, 5)
        assert updated is not None
        assert updated.current_offset == 5

    def test_update_offset_nonexistent(self) -> None:
        """Update offset returns None for nonexistent state."""
        manager = SearchStateManager()
        result = manager.update_offset("telegram:nonexistent", 5)
        assert result is None

    def test_update_offset_expired_state(self) -> None:
        """Update offset returns None for expired state."""
        manager = SearchStateManager(ttl_seconds=60)
        chat_id = "telegram:123456789"

        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        state = make_search_state(created_at=old_time)
        manager._states[chat_id] = state

        result = manager.update_offset(chat_id, 5)
        assert result is None
        # State should also be removed
        assert chat_id not in manager._states


class TestSearchStateManagerDelete:
    """Tests for delete operation."""

    def test_delete_existing_state(self) -> None:
        """Delete removes existing state."""
        manager = SearchStateManager()
        chat_id = "telegram:123456789"

        state = make_search_state()
        manager.save(chat_id, state)
        assert manager.get(chat_id) is not None

        manager.delete(chat_id)
        assert manager.get(chat_id) is None

    def test_delete_nonexistent_state(self) -> None:
        """Delete does nothing for nonexistent state."""
        manager = SearchStateManager()
        # Should not raise
        manager.delete("telegram:nonexistent")


class TestSearchStateChatIdFormat:
    """Tests for chat ID format handling."""

    def test_telegram_chat_id_format(self) -> None:
        """Telegram chat IDs work correctly."""
        manager = SearchStateManager()
        chat_id = "telegram:123456789"

        state = make_search_state()
        manager.save(chat_id, state)

        retrieved = manager.get(chat_id)
        assert retrieved is not None

    def test_slack_chat_id_format(self) -> None:
        """Slack channel IDs work correctly."""
        manager = SearchStateManager()
        chat_id = "slack:C0123456789"

        state = make_search_state()
        manager.save(chat_id, state)

        retrieved = manager.get(chat_id)
        assert retrieved is not None

    def test_different_platforms_separate_states(self) -> None:
        """Different platforms have separate state spaces."""
        manager = SearchStateManager()

        telegram_state = make_search_state(num_results=5)
        telegram_state.query = "telegram search"
        manager.save("telegram:123", telegram_state)

        slack_state = make_search_state(num_results=3)
        slack_state.query = "slack search"
        manager.save("slack:C123", slack_state)

        telegram_retrieved = manager.get("telegram:123")
        slack_retrieved = manager.get("slack:C123")

        assert telegram_retrieved is not None
        assert telegram_retrieved.query == "telegram search"
        assert slack_retrieved is not None
        assert slack_retrieved.query == "slack search"


class TestSearchStateMessageId:
    """Tests for message ID storage."""

    def test_telegram_message_id_int(self) -> None:
        """Telegram integer message IDs work."""
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=[],
            current_offset=0,
            message_id=12345,
        )
        assert state.message_id == 12345

    def test_slack_message_ts_string(self) -> None:
        """Slack timestamp message IDs work."""
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=[],
            current_offset=0,
            message_id="1706789012.123456",
        )
        assert state.message_id == "1706789012.123456"
