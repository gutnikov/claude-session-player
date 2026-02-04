"""Telegram message publisher using aiogram library."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from claude_session_player.watcher.deps import check_telegram_available

if TYPE_CHECKING:
    from aiogram.types import InlineKeyboardMarkup

    from claude_session_player.events import QuestionContent

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
# Question Keyboard Formatting
# ---------------------------------------------------------------------------


# Maximum number of buttons to show in the inline keyboard
MAX_QUESTION_BUTTONS = 5


def format_question_keyboard(
    content: QuestionContent,
) -> InlineKeyboardMarkup | None:
    """Create an inline keyboard for a question.

    Shows up to MAX_QUESTION_BUTTONS options as inline buttons.
    If the question has already been answered, returns None.

    Args:
        content: QuestionContent with questions and options.

    Returns:
        InlineKeyboardMarkup with option buttons, or None if answered.
    """
    # Don't show keyboard for answered questions
    if content.answers:
        return None

    # Import aiogram types lazily
    try:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    except ImportError:
        return None

    buttons: list[list[InlineKeyboardButton]] = []

    for q_idx, question in enumerate(content.questions):
        for opt_idx, option in enumerate(question.options[:MAX_QUESTION_BUTTONS]):
            # Callback data format: q:{tool_use_id}:{question_idx}:{option_idx}
            callback_data = f"q:{content.tool_use_id}:{q_idx}:{opt_idx}"
            # Truncate label to fit Telegram's 64-byte callback_data limit
            label = option.label
            if len(label) > 30:
                label = label[:27] + "..."
            buttons.append(
                [InlineKeyboardButton(text=label, callback_data=callback_data)]
            )

    if not buttons:
        return None

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_question_text(content: QuestionContent) -> str:
    """Format question text for Telegram display.

    Includes the question header, text, and overflow notice if there
    are more options than MAX_QUESTION_BUTTONS.

    Args:
        content: QuestionContent with questions and options.

    Returns:
        Formatted Telegram Markdown text.
    """
    lines: list[str] = []

    for question in content.questions:
        header = question.header or "Question"
        lines.append(f"❓ *{escape_markdown(header)}*")
        lines.append(escape_markdown(question.question))

        # Check for overflow options
        total_options = len(question.options)
        if total_options > MAX_QUESTION_BUTTONS:
            overflow_count = total_options - MAX_QUESTION_BUTTONS
            lines.append("")
            lines.append(f"_...and {overflow_count} more option{'s' if overflow_count > 1 else ''} in CLI_")
        lines.append("")

    lines.append("_(respond in CLI)_")
    return "\n".join(lines)


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
        reply_markup: InlineKeyboardMarkup | None = None,
        message_thread_id: int | None = None,
    ) -> int:
        """Send a new message to a chat or topic.

        Args:
            chat_id: Telegram chat ID.
            text: Message text (Markdown formatted).
            parse_mode: Telegram parse mode (default "Markdown").
            reply_markup: Optional inline keyboard markup.
            message_thread_id: Topic thread ID for supergroups with topics.

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
                reply_markup=reply_markup,
                message_thread_id=message_thread_id,
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
                    reply_markup=reply_markup,
                    message_thread_id=message_thread_id,
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
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> bool:
        """Edit an existing message.

        Args:
            chat_id: Telegram chat ID.
            message_id: ID of the message to edit.
            text: New message text (Markdown formatted).
            parse_mode: Telegram parse mode (default "Markdown").
            reply_markup: Optional inline keyboard markup (None to remove keyboard).

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
                reply_markup=reply_markup,
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
                    reply_markup=reply_markup,
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
