"""Search state manager for pagination state.

This module provides:
- SearchState: Stores an active search with results and pagination offset
- SearchStateManager: Manages search state per chat with TTL expiration
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .indexer import SessionInfo
from .search import SearchFilters


@dataclass
class SearchState:
    """State for an active search in a chat.

    Stores the full result list and tracks pagination offset,
    allowing pagination buttons to navigate without re-executing the search.
    """

    query: str
    filters: SearchFilters
    results: list[SessionInfo]
    current_offset: int
    message_id: int | str  # Slack ts or Telegram message_id
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get_page(self, limit: int = 5) -> list[SessionInfo]:
        """Get the current page of results.

        Args:
            limit: Maximum number of results per page.

        Returns:
            List of sessions for the current page.
        """
        return self.results[self.current_offset : self.current_offset + limit]

    def session_at_index(self, index: int) -> SessionInfo | None:
        """Get session by page-relative index (0-4).

        Args:
            index: The page-relative index (0-based).

        Returns:
            SessionInfo if index is valid, None otherwise.
        """
        actual_index = self.current_offset + index
        if 0 <= actual_index < len(self.results):
            return self.results[actual_index]
        return None

    def has_next_page(self, limit: int = 5) -> bool:
        """Check if there are more results after the current page.

        Args:
            limit: Results per page.

        Returns:
            True if there are more results.
        """
        return self.current_offset + limit < len(self.results)

    def has_prev_page(self) -> bool:
        """Check if there are results before the current page.

        Returns:
            True if not on the first page.
        """
        return self.current_offset > 0


class SearchStateManager:
    """Manages search state for active searches.

    Stores one search state per chat, with automatic TTL expiration.
    Thread-safe for concurrent access.
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        """Initialize the manager.

        Args:
            ttl_seconds: Time-to-live for search states (default: 5 minutes).
        """
        self._states: dict[str, SearchState] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def save(self, chat_id: str, state: SearchState) -> None:
        """Save or update search state for a chat.

        A new search replaces any previous state for the same chat.
        Also cleans up expired states from other chats.

        Args:
            chat_id: The chat identifier (e.g., "telegram:123456789").
            state: The search state to save.
        """
        with self._lock:
            self._states[chat_id] = state
            self._cleanup_expired()

    def get(self, chat_id: str) -> SearchState | None:
        """Get search state for a chat.

        Args:
            chat_id: The chat identifier.

        Returns:
            SearchState if found and not expired, None otherwise.
        """
        with self._lock:
            state = self._states.get(chat_id)
            if state is None:
                return None

            # Check if expired
            age = (datetime.now(timezone.utc) - state.created_at).total_seconds()
            if age > self._ttl:
                del self._states[chat_id]
                return None

            return state

    def update_offset(self, chat_id: str, new_offset: int) -> SearchState | None:
        """Update pagination offset for a chat's search state.

        Args:
            chat_id: The chat identifier.
            new_offset: The new offset to set.

        Returns:
            Updated SearchState if found and not expired, None otherwise.
        """
        with self._lock:
            state = self._states.get(chat_id)
            if state is None:
                return None

            # Check if expired
            age = (datetime.now(timezone.utc) - state.created_at).total_seconds()
            if age > self._ttl:
                del self._states[chat_id]
                return None

            state.current_offset = new_offset
            return state

    def delete(self, chat_id: str) -> None:
        """Remove search state for a chat.

        Args:
            chat_id: The chat identifier.
        """
        with self._lock:
            self._states.pop(chat_id, None)

    def _cleanup_expired(self) -> None:
        """Remove all expired states.

        Note: Must be called with lock held.
        """
        now = datetime.now(timezone.utc)
        expired = [
            chat_id
            for chat_id, state in self._states.items()
            if (now - state.created_at).total_seconds() > self._ttl
        ]
        for chat_id in expired:
            del self._states[chat_id]
