"""Message debouncer for rate-limiting message updates.

This module provides debouncing functionality to prevent hitting Telegram and Slack
rate limits when rapid events cause frequent message updates.

Rate limits (we target 50% of actual limits):
- Telegram: ~30 messages/sec per chat (we target 15/sec = 67ms minimum interval)
- Slack: ~1 request/sec per channel (we target 0.5/sec = 2000ms minimum interval)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

logger = logging.getLogger(__name__)

# Type alias for destination types
DestinationType = Literal["telegram", "slack"]


@dataclass
class PendingUpdate:
    """Tracks a pending debounced update."""

    task: asyncio.Task[None]
    update_fn: Callable[[], Awaitable[None]]
    content: Any


class MessageDebouncer:
    """Debounces message updates to prevent rate limiting.

    This class manages debounced updates per message per destination.
    New message creation is immediate (not debounced), but subsequent
    updates to the same message are debounced.

    Additionally, this class tracks the last pushed content per message
    and skips scheduling updates if the content is unchanged. This prevents
    unnecessary API calls when the same content would be pushed multiple times.

    Attributes:
        telegram_delay_ms: Debounce delay for Telegram updates (default: 500ms)
        slack_delay_ms: Debounce delay for Slack updates (default: 2000ms)
    """

    def __init__(
        self,
        telegram_delay_ms: int = 500,
        slack_delay_ms: int = 2000,
    ) -> None:
        """Initialize the debouncer with configurable delays.

        Args:
            telegram_delay_ms: Debounce delay for Telegram in milliseconds
            slack_delay_ms: Debounce delay for Slack in milliseconds
        """
        self._telegram_delay = telegram_delay_ms / 1000
        self._slack_delay = slack_delay_ms / 1000

        # Pending updates: (destination_type, identifier, message_id) -> PendingUpdate
        self._pending: dict[tuple[str, str, str], PendingUpdate] = {}

        # Last pushed content per message for change detection
        # Key: (destination_type, identifier, message_id) -> content string
        self._last_pushed_content: dict[tuple[str, str, str], str] = {}

    def _get_delay(self, destination_type: DestinationType) -> float:
        """Get the delay in seconds for a destination type."""
        return self._telegram_delay if destination_type == "telegram" else self._slack_delay

    async def schedule_update(
        self,
        destination_type: DestinationType,
        identifier: str,
        message_id: str,
        update_fn: Callable[[], Awaitable[None]],
        content: Any,
    ) -> bool:
        """Schedule a debounced update.

        If an update is already pending for this message, cancel it and
        schedule a new one with the latest content. The update function
        will be called after the debounce delay expires.

        If the content is identical to the last pushed content for this
        message, the update is skipped entirely (no scheduling, no API call).

        Args:
            destination_type: "telegram" or "slack"
            identifier: chat_id (Telegram) or channel (Slack)
            message_id: The message being updated
            update_fn: Async function to call when debounce expires.
                       This function should capture the content it needs.
            content: The latest content (stored for potential inspection/coalescing).
                     Used for change detection - should be a string for comparison.

        Returns:
            True if update was scheduled, False if skipped due to unchanged content.
        """
        key = (destination_type, identifier, message_id)

        # Check if content is unchanged from last push
        # Content must be a string for change detection to work
        if isinstance(content, str) and key in self._last_pushed_content:
            if content == self._last_pushed_content[key]:
                logger.debug(
                    "Skipped update for %s/%s/%s: content unchanged",
                    destination_type,
                    identifier,
                    message_id,
                )
                return False

        # Cancel existing pending update if any
        if key in self._pending:
            old_update = self._pending[key]
            old_update.task.cancel()
            try:
                await old_update.task
            except asyncio.CancelledError:
                pass
            logger.debug(
                "Cancelled pending update for %s/%s/%s",
                destination_type,
                identifier,
                message_id,
            )

        # Determine delay based on destination type
        delay = self._get_delay(destination_type)

        # Create the delayed update task
        async def _delayed_update() -> None:
            await asyncio.sleep(delay)
            # Remove from pending before executing
            if key in self._pending:
                del self._pending[key]
            try:
                await update_fn()
                # Update last pushed content after successful push
                if isinstance(content, str):
                    self._last_pushed_content[key] = content
                logger.debug(
                    "Executed debounced update for %s/%s/%s",
                    destination_type,
                    identifier,
                    message_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to execute update for %s/%s/%s: %s",
                    destination_type,
                    identifier,
                    message_id,
                    e,
                )

        task = asyncio.create_task(_delayed_update())
        self._pending[key] = PendingUpdate(task=task, update_fn=update_fn, content=content)
        logger.debug(
            "Scheduled debounced update for %s/%s/%s (delay: %.2fs)",
            destination_type,
            identifier,
            message_id,
            delay,
        )
        return True

    async def flush(self, session_id: str | None = None) -> None:
        """Flush all pending updates immediately.

        Cancels all pending delayed tasks and executes the updates
        immediately with the latest content.

        Args:
            session_id: Optional filter (currently unused, reserved for future use)
        """
        if not self._pending:
            return

        # Collect all pending updates to execute
        to_execute: list[tuple[tuple[str, str, str], PendingUpdate]] = list(self._pending.items())
        self._pending.clear()

        # Cancel all tasks and execute updates immediately
        for key, pending in to_execute:
            pending.task.cancel()
            try:
                await pending.task
            except asyncio.CancelledError:
                pass

            # Execute update immediately
            try:
                await pending.update_fn()
                # Update last pushed content after successful flush
                if isinstance(pending.content, str):
                    self._last_pushed_content[key] = pending.content
                logger.debug(
                    "Flushed update for %s/%s/%s",
                    key[0],
                    key[1],
                    key[2],
                )
            except Exception as e:
                logger.warning(
                    "Failed to flush update for %s/%s/%s: %s",
                    key[0],
                    key[1],
                    key[2],
                    e,
                )

    async def cancel_all(self) -> None:
        """Cancel all pending updates without executing them.

        Use this for clean shutdown when updates should not be delivered.
        """
        if not self._pending:
            return

        # Cancel all tasks
        for key, pending in list(self._pending.items()):
            pending.task.cancel()
            try:
                await pending.task
            except asyncio.CancelledError:
                pass
            logger.debug(
                "Cancelled update for %s/%s/%s (shutdown)",
                key[0],
                key[1],
                key[2],
            )

        self._pending.clear()

    def pending_count(self) -> int:
        """Return the number of pending updates."""
        return len(self._pending)

    def has_pending(self, destination_type: str, identifier: str, message_id: str) -> bool:
        """Check if there's a pending update for a specific message."""
        return (destination_type, identifier, message_id) in self._pending

    def get_pending_content(
        self, destination_type: str, identifier: str, message_id: str
    ) -> Any | None:
        """Get the latest pending content for a message, if any."""
        key = (destination_type, identifier, message_id)
        if key in self._pending:
            return self._pending[key].content
        return None

    def clear_content(
        self, destination_type: str, identifier: str, message_id: str
    ) -> None:
        """Clear the tracked last pushed content for a message.

        Call this when a message binding is removed to free memory.
        This removes the change detection tracking for the specified message.

        Args:
            destination_type: "telegram" or "slack"
            identifier: chat_id (Telegram) or channel (Slack)
            message_id: The message ID to clear tracking for
        """
        key = (destination_type, identifier, message_id)
        if key in self._last_pushed_content:
            del self._last_pushed_content[key]
            logger.debug(
                "Cleared content tracking for %s/%s/%s",
                destination_type,
                identifier,
                message_id,
            )

    def get_last_pushed_content(
        self, destination_type: str, identifier: str, message_id: str
    ) -> str | None:
        """Get the last pushed content for a message, if any.

        This is useful for testing and debugging change detection.

        Args:
            destination_type: "telegram" or "slack"
            identifier: chat_id (Telegram) or channel (Slack)
            message_id: The message ID to query

        Returns:
            The last pushed content string, or None if not tracked.
        """
        key = (destination_type, identifier, message_id)
        return self._last_pushed_content.get(key)
