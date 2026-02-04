"""Message binding model for single-message session rendering.

Binds messages to sessions with a specific display preset.
Each binding tracks the message ID, last pushed content, and TTL state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from claude_session_player.watcher.destinations import AttachedDestination


Preset = Literal["desktop", "mobile"]

# Maximum TTL cap in seconds (5 minutes)
MAX_TTL_SECONDS = 300

# Default TTL in seconds
DEFAULT_TTL_SECONDS = 30


@dataclass
class MessageBinding:
    """Binding between a session, preset, destination, and message.

    Attributes:
        session_id: The session being displayed.
        preset: Display preset ("desktop" or "mobile").
        destination: The messaging destination (Telegram chat or Slack channel).
        message_id: The platform message ID (Telegram message_id or Slack ts).
        last_content: The last content pushed to this message.
        created_at: Timestamp when the binding was created.
        ttl_seconds: Time-to-live in seconds (default 30, max 300).
        expired: Whether the binding has been marked as expired.
    """

    session_id: str
    preset: Preset
    destination: AttachedDestination
    message_id: str
    last_content: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    expired: bool = False

    def is_expired(self) -> bool:
        """Check if TTL has passed.

        Returns:
            True if the binding has expired or TTL has elapsed.
        """
        if self.expired:
            return True
        now = datetime.now(timezone.utc)
        expiry_time = self.created_at + timedelta(seconds=self.ttl_seconds)
        return now > expiry_time

    def extend_ttl(self, seconds: int = DEFAULT_TTL_SECONDS) -> None:
        """Extend TTL by given seconds, capped at MAX_TTL_SECONDS.

        Args:
            seconds: Number of seconds to add to TTL.
        """
        self.ttl_seconds = min(self.ttl_seconds + seconds, MAX_TTL_SECONDS)
        self.expired = False

    def time_remaining(self) -> int:
        """Return seconds remaining, or 0 if expired.

        Returns:
            Number of seconds until expiry, or 0 if already expired.
        """
        if self.expired:
            return 0
        now = datetime.now(timezone.utc)
        expiry_time = self.created_at + timedelta(seconds=self.ttl_seconds)
        remaining = (expiry_time - now).total_seconds()
        return max(0, int(remaining))


@dataclass
class MessageBindingManager:
    """Manages message bindings for all sessions.

    Tracks which messages are bound to which sessions and presets.
    Provides methods to add, remove, and query bindings.
    """

    # Map from session_id to list of bindings for that session
    _bindings: dict[str, list[MessageBinding]] = field(
        default_factory=dict, init=False
    )

    def add_binding(self, binding: MessageBinding) -> None:
        """Add a new message binding.

        Args:
            binding: The binding to add.
        """
        self._bindings.setdefault(binding.session_id, []).append(binding)

    def remove_binding(
        self, session_id: str, destination: AttachedDestination
    ) -> MessageBinding | None:
        """Remove a binding by session and destination.

        Args:
            session_id: Session identifier.
            destination: The destination to remove.

        Returns:
            The removed binding, or None if not found.
        """
        bindings = self._bindings.get(session_id, [])
        for i, binding in enumerate(bindings):
            if (
                binding.destination.type == destination.type
                and binding.destination.identifier == destination.identifier
            ):
                return bindings.pop(i)
        return None

    def get_bindings_for_session(self, session_id: str) -> list[MessageBinding]:
        """Get all bindings for a session.

        Args:
            session_id: Session identifier.

        Returns:
            List of bindings (empty if no bindings exist).
        """
        return list(self._bindings.get(session_id, []))

    def get_all_bindings(self) -> list[MessageBinding]:
        """Get all bindings across all sessions.

        Returns:
            List of all bindings.
        """
        result: list[MessageBinding] = []
        for bindings in self._bindings.values():
            result.extend(bindings)
        return result

    def update_last_content(
        self, session_id: str, destination: AttachedDestination, content: str
    ) -> None:
        """Update the last_content field for a binding.

        Args:
            session_id: Session identifier.
            destination: The destination to update.
            content: The new content value.
        """
        bindings = self._bindings.get(session_id, [])
        for binding in bindings:
            if (
                binding.destination.type == destination.type
                and binding.destination.identifier == destination.identifier
            ):
                binding.last_content = content
                return

    def find_binding(
        self, session_id: str, destination: AttachedDestination
    ) -> MessageBinding | None:
        """Find a binding by session and destination.

        Args:
            session_id: Session identifier.
            destination: The destination to find.

        Returns:
            The matching binding, or None if not found.
        """
        bindings = self._bindings.get(session_id, [])
        for binding in bindings:
            if (
                binding.destination.type == destination.type
                and binding.destination.identifier == destination.identifier
            ):
                return binding
        return None

    def has_bindings(self, session_id: str) -> bool:
        """Check if a session has any bindings.

        Args:
            session_id: Session identifier.

        Returns:
            True if the session has at least one binding.
        """
        return bool(self._bindings.get(session_id))

    def clear_session(self, session_id: str) -> list[MessageBinding]:
        """Remove all bindings for a session.

        Args:
            session_id: Session identifier.

        Returns:
            List of removed bindings.
        """
        return self._bindings.pop(session_id, [])

    def find_binding_by_message_id(
        self, destination_type: str, identifier: str, message_id: str
    ) -> MessageBinding | None:
        """Find binding by destination and message_id (for callback handlers).

        This method is used by Telegram/Slack callback handlers to find
        the binding associated with a specific message.

        Args:
            destination_type: Type of destination ("telegram" or "slack").
            identifier: Destination identifier (chat_id or channel).
            message_id: The platform message ID.

        Returns:
            The matching binding, or None if not found.
        """
        for bindings in self._bindings.values():
            for binding in bindings:
                if (
                    binding.destination.type == destination_type
                    and binding.destination.identifier == identifier
                    and binding.message_id == message_id
                ):
                    return binding
        return None
