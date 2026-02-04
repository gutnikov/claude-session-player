"""Message binding model for single-message session rendering.

Binds messages to sessions with a specific display preset.
Each binding tracks the message ID and last pushed content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from claude_session_player.watcher.destinations import AttachedDestination


Preset = Literal["desktop", "mobile"]


@dataclass
class MessageBinding:
    """Binding between a session, preset, destination, and message.

    Attributes:
        session_id: The session being displayed.
        preset: Display preset ("desktop" or "mobile").
        destination: The messaging destination (Telegram chat or Slack channel).
        message_id: The platform message ID (Telegram message_id or Slack ts).
        last_content: The last content pushed to this message.
    """

    session_id: str
    preset: Preset
    destination: AttachedDestination
    message_id: str
    last_content: str = ""


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
