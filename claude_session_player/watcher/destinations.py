"""Destination manager for attach/detach lifecycle."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from claude_session_player.watcher.config import (
    ConfigManager,
    SlackDestination,
    TelegramDestination,
)


# ---------------------------------------------------------------------------
# Telegram Identifier Helpers
# ---------------------------------------------------------------------------


def make_telegram_identifier(chat_id: str, thread_id: int | None = None) -> str:
    """Create identifier from chat_id and optional thread_id.

    Args:
        chat_id: Telegram chat ID (may be negative for groups).
        thread_id: Topic thread ID, or None for General/non-forum.

    Returns:
        Combined identifier string.
    """
    if thread_id is not None:
        return f"{chat_id}:{thread_id}"
    return chat_id


def parse_telegram_identifier(identifier: str) -> tuple[str, int | None]:
    """Parse identifier into (chat_id, thread_id).

    Uses rsplit to handle negative chat_ids correctly.

    Args:
        identifier: Combined identifier string.

    Returns:
        Tuple of (chat_id, thread_id or None).
    """
    if ":" in identifier:
        chat_id, thread_str = identifier.rsplit(":", 1)
        try:
            return chat_id, int(thread_str)
        except ValueError:
            return identifier, None
    return identifier, None


@dataclass
class AttachedDestination:
    """A single attached destination."""

    type: Literal["telegram", "slack"]
    identifier: str  # chat_id for telegram, channel for slack
    attached_at: datetime


@dataclass
class DestinationManager:
    """Manages the lifecycle of messaging destinations attached to sessions.

    Tracks which destinations are attached to which sessions and coordinates
    with ConfigManager for persistence.
    """

    _config: ConfigManager
    _on_session_start: Callable[[str, Path], Awaitable[None]]

    # Runtime state (in-memory)
    _destinations: dict[str, list[AttachedDestination]] = field(
        default_factory=dict, init=False
    )

    def _find_destination(
        self, session_id: str, destination_type: str, identifier: str
    ) -> AttachedDestination | None:
        """Find a destination by session, type, and identifier.

        Args:
            session_id: Session identifier.
            destination_type: "telegram" or "slack".
            identifier: chat_id or channel.

        Returns:
            AttachedDestination if found, None otherwise.
        """
        destinations = self._destinations.get(session_id, [])
        for dest in destinations:
            if dest.type == destination_type and dest.identifier == identifier:
                return dest
        return None

    async def attach(
        self,
        session_id: str,
        path: Path | None,
        destination_type: str,
        identifier: str,
    ) -> bool:
        """Attach a destination to a session.

        Args:
            session_id: Session identifier.
            path: Path to JSONL file (required if session not yet known).
            destination_type: "telegram" or "slack".
            identifier: chat_id or channel.

        Returns:
            True if newly attached, False if already attached (idempotent).

        Raises:
            ValueError: If session unknown and path not provided.
            ValueError: If destination_type invalid.
        """
        # Validate destination_type
        if destination_type not in ("telegram", "slack"):
            raise ValueError(f"Invalid destination_type: {destination_type}")

        # 1. Check if already attached (idempotent)
        existing = self._find_destination(session_id, destination_type, identifier)
        if existing:
            return False  # Already attached

        # 2. If first destination for this session, start file watching
        is_first = (
            session_id not in self._destinations
            or not self._destinations[session_id]
        )
        if is_first:
            if path is None:
                # Try to get from config
                session_config = self._config.get(session_id)
                if not session_config:
                    raise ValueError(
                        f"Session {session_id} unknown and no path provided"
                    )
                path = session_config.path
            await self._on_session_start(session_id, path)

        # 3. Add destination to runtime state
        dest = AttachedDestination(
            type=destination_type,  # type: ignore[arg-type]
            identifier=identifier,
            attached_at=datetime.now(),
        )
        self._destinations.setdefault(session_id, []).append(dest)

        # 4. Persist to config
        if destination_type == "telegram":
            # Parse identifier to extract chat_id and optional thread_id
            chat_id, thread_id = parse_telegram_identifier(identifier)
            config_dest = TelegramDestination(chat_id=chat_id, thread_id=thread_id)
        else:
            config_dest = SlackDestination(channel=identifier)
        self._config.add_destination(session_id, config_dest, path)

        return True

    async def detach(
        self,
        session_id: str,
        destination_type: str,
        identifier: str,
    ) -> bool:
        """Detach a destination from a session.

        Args:
            session_id: Session identifier.
            destination_type: "telegram" or "slack".
            identifier: chat_id or channel.

        Returns:
            True if detached, False if not found.
        """
        # 1. Find and remove destination
        destinations = self._destinations.get(session_id, [])
        dest = self._find_destination(session_id, destination_type, identifier)
        if not dest:
            return False

        destinations.remove(dest)

        # 2. Remove from config
        if destination_type == "telegram":
            # Parse identifier to extract chat_id and optional thread_id
            chat_id, thread_id = parse_telegram_identifier(identifier)
            config_dest = TelegramDestination(chat_id=chat_id, thread_id=thread_id)
        else:
            config_dest = SlackDestination(channel=identifier)
        self._config.remove_destination(session_id, config_dest)

        return True

    def get_destinations(
        self,
        session_id: str,
    ) -> list[AttachedDestination]:
        """Get all attached destinations for a session.

        Args:
            session_id: Session identifier.

        Returns:
            List of AttachedDestination objects.
        """
        return list(self._destinations.get(session_id, []))

    def get_destinations_by_type(
        self,
        session_id: str,
        destination_type: str,
    ) -> list[AttachedDestination]:
        """Get destinations of a specific type.

        Args:
            session_id: Session identifier.
            destination_type: "telegram" or "slack".

        Returns:
            List of AttachedDestination objects of the given type.
        """
        return [
            d
            for d in self._destinations.get(session_id, [])
            if d.type == destination_type
        ]

    async def restore_from_config(self) -> None:
        """Restore destinations from persisted config on startup.

        Called by WatcherService during initialization.
        """
        sessions = self._config.load()
        for session in sessions:
            has_telegram = bool(session.destinations.telegram)
            has_slack = bool(session.destinations.slack)
            if has_telegram or has_slack:
                # Start file watching
                await self._on_session_start(session.session_id, session.path)

                # Populate runtime state
                self._destinations[session.session_id] = []
                for tg in session.destinations.telegram:
                    self._destinations[session.session_id].append(
                        AttachedDestination(
                            type="telegram",
                            identifier=tg.identifier,  # Uses combined identifier
                            attached_at=datetime.now(),
                        )
                    )
                for slack in session.destinations.slack:
                    self._destinations[session.session_id].append(
                        AttachedDestination(
                            type="slack",
                            identifier=slack.channel,
                            attached_at=datetime.now(),
                        )
                    )

    def has_destinations(self, session_id: str) -> bool:
        """Check if session has any attached destinations.

        Args:
            session_id: Session identifier.

        Returns:
            True if session has at least one attached destination.
        """
        destinations = self._destinations.get(session_id, [])
        return len(destinations) > 0
