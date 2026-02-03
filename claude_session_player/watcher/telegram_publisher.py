"""Telegram message publisher using aiogram library."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from claude_session_player.watcher.deps import check_telegram_available

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class TelegramError(Exception):
    """Base exception for Telegram operations."""

    pass


class TelegramAuthError(TelegramError):
    """Bot authentication/validation failed."""

    pass


# ---------------------------------------------------------------------------
# Message Formatting Utilities
# ---------------------------------------------------------------------------


# Characters that need escaping in Telegram Markdown V1
# Reference: https://core.telegram.org/bots/api#markdown-style
_MARKDOWN_ESCAPE_CHARS = re.compile(r"([_*`\[])")


def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram Markdown.

    Escapes: _ * ` [

    Args:
        text: Raw text to escape.

    Returns:
        Text with special characters escaped.
    """
    return _MARKDOWN_ESCAPE_CHARS.sub(r"\\\1", text)


@dataclass
class ToolCallInfo:
    """Information about a tool call for formatting."""

    name: str
    label: str
    icon: str
    result: str | None = None
    is_error: bool = False


# Tool name to icon mapping
_TOOL_ICONS = {
    "Read": "📖",
    "Write": "📝",
    "Edit": "✏️",
    "Bash": "🔧",
    "Glob": "🔍",
    "Grep": "🔍",
    "Task": "🤖",
    "WebSearch": "🌐",
    "WebFetch": "🌐",
}


def get_tool_icon(tool_name: str) -> str:
    """Get the icon for a tool name.

    Args:
        tool_name: Name of the tool.

    Returns:
        Emoji icon for the tool.
    """
    return _TOOL_ICONS.get(tool_name, "⚙️")


def format_user_message(text: str) -> str:
    """Format a user message for Telegram.

    Args:
        text: User message text.

    Returns:
        Formatted Telegram Markdown message.
    """
    escaped = escape_markdown(text)
    return f"👤 *User*\n\n{escaped}"


def format_turn_message(
    assistant_text: str | None,
    tool_calls: list[ToolCallInfo],
    duration_ms: int | None,
) -> str:
    """Format a complete turn message for Telegram.

    Args:
        assistant_text: Optional assistant response text.
        tool_calls: List of tool call information.
        duration_ms: Optional turn duration in milliseconds.

    Returns:
        Formatted Telegram Markdown message.
    """
    parts = ["🤖 *Assistant*"]

    if assistant_text:
        parts.append(f"\n\n{escape_markdown(assistant_text)}")

    for tool in tool_calls:
        parts.append("\n\n───────────────")
        parts.append(f"\n{tool.icon} *{escape_markdown(tool.name)}* `{escape_markdown(tool.label)}`")
        if tool.result:
            # Truncate long results
            result = tool.result[:500]
            if len(tool.result) > 500:
                result += "..."
            result = escape_markdown(result)
            parts.append(f"\n✓ {result}")
        elif tool.is_error:
            parts.append("\n✗ Error")

    if duration_ms:
        seconds = duration_ms / 1000
        parts.append(f"\n\n_⏱ {seconds:.1f}s_")

    return "".join(parts)


def format_system_message(text: str) -> str:
    """Format a system message for Telegram.

    Args:
        text: System message text.

    Returns:
        Formatted Telegram Markdown message.
    """
    return f"⚡ *{escape_markdown(text)}*"


def format_context_compacted() -> str:
    """Format context compaction notice for Telegram.

    Returns:
        Formatted Telegram Markdown message.
    """
    return "⚡ *Context compacted* — previous messages cleared"


# ---------------------------------------------------------------------------
# TelegramPublisher
# ---------------------------------------------------------------------------


# Maximum message length for Telegram
_MAX_MESSAGE_LENGTH = 4096


def _truncate_message(text: str, max_length: int = _MAX_MESSAGE_LENGTH) -> str:
    """Truncate message to fit Telegram's character limit.

    Args:
        text: Message text to truncate.
        max_length: Maximum length (default 4096).

    Returns:
        Truncated message with indicator if needed.
    """
    if len(text) <= max_length:
        return text
    # Leave room for truncation indicator
    return text[: max_length - 20] + "\n\n... [truncated]"


class TelegramPublisher:
    """Publisher for sending messages via Telegram Bot API.

    Uses aiogram library for async Telegram API communication.
    Handles validation, sending, editing, and retrying messages.
    """

    def __init__(self, token: str | None = None) -> None:
        """Initialize the publisher.

        Args:
            token: Telegram bot token from BotFather.
        """
        self._token = token
        self._bot: object | None = None  # aiogram.Bot when available
        self._validated = False

    async def validate(self) -> None:
        """Validate bot credentials by calling getMe.

        Raises:
            ValueError: If token not configured.
            TelegramAuthError: If token invalid or bot unauthorized.
            TelegramError: If aiogram is not installed.
        """
        if not self._token:
            raise ValueError("Telegram bot token not configured")

        if self._validated:
            return

        if not check_telegram_available():
            raise TelegramError(
                "aiogram library not installed. Install with: pip install aiogram"
            )

        try:
            from aiogram import Bot
            from aiogram.exceptions import TelegramAPIError

            self._bot = Bot(token=self._token)
            me = await self._bot.get_me()
            logger.info(f"Telegram bot validated: @{me.username}")
            self._validated = True
        except TelegramAPIError as e:
            raise TelegramAuthError(f"Bot validation failed: {e}") from e

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown",
    ) -> int:
        """Send a new message to a chat.

        Args:
            chat_id: Telegram chat ID.
            text: Message text (Markdown formatted).
            parse_mode: Telegram parse mode (default "Markdown").

        Returns:
            message_id of the sent message.

        Raises:
            TelegramError: On API failure after retry.
        """
        if not self._validated:
            await self.validate()

        # Truncate if needed
        text = _truncate_message(text)

        from aiogram.exceptions import TelegramAPIError

        try:
            result = await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
            )
            return result.message_id
        except TelegramAPIError:
            # Retry once after a short delay
            await asyncio.sleep(1)
            try:
                result = await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                )
                return result.message_id
            except TelegramAPIError as e2:
                logger.warning(f"Failed to send Telegram message to {chat_id}: {e2}")
                raise TelegramError(f"Send failed: {e2}") from e2

    async def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        parse_mode: str = "Markdown",
    ) -> bool:
        """Edit an existing message.

        Args:
            chat_id: Telegram chat ID.
            message_id: ID of the message to edit.
            text: New message text (Markdown formatted).
            parse_mode: Telegram parse mode (default "Markdown").

        Returns:
            True if edited successfully, False if message not found/editable.
        """
        if not self._validated:
            await self.validate()

        # Truncate if needed
        text = _truncate_message(text)

        from aiogram.exceptions import TelegramAPIError

        try:
            await self._bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
            )
            return True
        except TelegramAPIError as e:
            error_str = str(e).lower()
            if "message is not modified" in error_str:
                return True  # Content unchanged, that's fine
            if "message to edit not found" in error_str:
                return False  # Message deleted or too old

            # Retry once for other errors
            await asyncio.sleep(1)
            try:
                await self._bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=parse_mode,
                )
                return True
            except TelegramAPIError as e2:
                logger.warning(f"Failed to edit Telegram message {message_id}: {e2}")
                return False

    async def close(self) -> None:
        """Close the bot session."""
        if self._bot is not None:
            await self._bot.session.close()
            self._bot = None
            self._validated = False
