"""Slack message publisher using slack-sdk library."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from claude_session_player.watcher.deps import check_slack_available

if TYPE_CHECKING:
    from claude_session_player.events import QuestionContent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class SlackError(Exception):
    """Base exception for Slack operations."""

    pass


class SlackAuthError(SlackError):
    """Bot authentication/validation failed."""

    pass


# ---------------------------------------------------------------------------
# Message Formatting Utilities (Block Kit)
# ---------------------------------------------------------------------------


def escape_mrkdwn(text: str) -> str:
    """Escape Slack mrkdwn special characters.

    Escapes: & < >

    Args:
        text: Raw text to escape.

    Returns:
        Text with special characters escaped.
    """
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


@dataclass
class ToolCallInfo:
    """Information about a tool call for formatting."""

    name: str
    label: str
    icon: str
    result: str | None = None
    is_error: bool = False


# Tool name to icon mapping (same as Telegram)
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


def format_user_message_blocks(text: str) -> list[dict]:
    """Format a user message as Block Kit blocks.

    Args:
        text: User message text.

    Returns:
        List of Block Kit blocks.
    """
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"👤 *User*\n\n{escape_mrkdwn(text)}"},
        }
    ]


def format_turn_message_blocks(
    assistant_text: str | None,
    tool_calls: list[ToolCallInfo],
    duration_ms: int | None,
) -> list[dict]:
    """Format a complete turn message as Block Kit blocks.

    Args:
        assistant_text: Optional assistant response text.
        tool_calls: List of tool call information.
        duration_ms: Optional turn duration in milliseconds.

    Returns:
        List of Block Kit blocks.
    """
    blocks: list[dict] = []

    # Assistant header + text
    header_text = "🤖 *Assistant*"
    if assistant_text:
        header_text += f"\n\n{escape_mrkdwn(assistant_text)}"
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": header_text}})

    # Tool calls
    for tool in tool_calls:
        blocks.append({"type": "divider"})
        tool_text = f"{tool.icon} *{tool.name}* `{tool.label}`"
        if tool.result:
            # Truncate long results
            result = escape_mrkdwn(tool.result[:1000])
            if len(tool.result) > 1000:
                result += "..."
            tool_text += f"\n✓ {result}"
        elif tool.is_error:
            tool_text += "\n✗ Error"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": tool_text}})

    # Duration footer
    if duration_ms:
        seconds = duration_ms / 1000
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"⏱ {seconds:.1f}s"}],
            }
        )

    return blocks


def format_system_message_blocks(text: str) -> list[dict]:
    """Format a system message as Block Kit blocks.

    Args:
        text: System message text.

    Returns:
        List of Block Kit blocks.
    """
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"⚡ *{escape_mrkdwn(text)}*"},
        }
    ]


def format_context_compacted_blocks() -> list[dict]:
    """Format context compaction notice as Block Kit blocks.

    Returns:
        List of Block Kit blocks.
    """
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⚡ *Context compacted* — previous messages cleared",
            },
        }
    ]


# ---------------------------------------------------------------------------
# Question Block Kit Formatting
# ---------------------------------------------------------------------------


# Maximum number of buttons per actions block for questions
MAX_QUESTION_BUTTONS = 5


def format_question_blocks(content: QuestionContent) -> list[dict]:
    """Format question blocks with action buttons for Slack.

    Builds Block Kit blocks with inline action buttons for unanswered questions.
    Each question gets a section with header and text, followed by an actions
    block with buttons for options (up to MAX_QUESTION_BUTTONS).

    Args:
        content: QuestionContent with questions and options.

    Returns:
        List of Block Kit blocks.
    """
    blocks: list[dict] = []

    for q_idx, question in enumerate(content.questions):
        header = question.header or "Question"

        # Section with question header and text
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":question: *{escape_mrkdwn(header)}*\n{escape_mrkdwn(question.question)}",
            },
        })

        # Actions block with option buttons
        buttons: list[dict] = []
        for opt_idx, option in enumerate(question.options[:MAX_QUESTION_BUTTONS]):
            # Truncate label to fit Slack's button text limit (75 chars)
            label = option.label
            if len(label) > 30:
                label = label[:27] + "..."
            buttons.append({
                "type": "button",
                "text": {"type": "plain_text", "text": label, "emoji": True},
                "action_id": f"question_opt_{q_idx}_{opt_idx}",
                "value": f"{content.tool_use_id}:{q_idx}:{opt_idx}",
            })

        if buttons:
            blocks.append({
                "type": "actions",
                "block_id": f"q_{content.tool_use_id}_{q_idx}",
                "elements": buttons,
            })

        # Overflow notice if more than MAX_QUESTION_BUTTONS options
        total_options = len(question.options)
        if total_options > MAX_QUESTION_BUTTONS:
            overflow_count = total_options - MAX_QUESTION_BUTTONS
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"_and {overflow_count} more option{'s' if overflow_count > 1 else ''} in CLI_",
                }],
            })

        # Divider between questions (not after last)
        if q_idx < len(content.questions) - 1:
            blocks.append({"type": "divider"})

    # Final context prompting CLI response
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "_respond in CLI_"}],
    })

    return blocks


def format_answered_question_blocks(content: QuestionContent) -> list[dict]:
    """Format answered question blocks for Slack (no action buttons).

    Builds Block Kit blocks showing answered questions with the selected
    answer displayed. Does not include action buttons.

    Args:
        content: QuestionContent with questions and answers.

    Returns:
        List of Block Kit blocks.
    """
    blocks: list[dict] = []

    for question in content.questions:
        header = question.header or "Question"

        # Build section text with question header and text
        section_text = f":question: *{escape_mrkdwn(header)}*\n{escape_mrkdwn(question.question)}"
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": section_text},
        })

        # Show the selected answer
        answer = content.answers.get(question.question) if content.answers else None
        if answer:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":white_check_mark: Selected: _{escape_mrkdwn(answer)}_",
                },
            })

    return blocks


# ---------------------------------------------------------------------------
# SlackPublisher
# ---------------------------------------------------------------------------


# Maximum blocks per message for Slack
_MAX_BLOCKS = 50


def _truncate_blocks(blocks: list[dict], max_blocks: int = _MAX_BLOCKS) -> list[dict]:
    """Truncate blocks list to fit Slack's block limit.

    Args:
        blocks: List of Block Kit blocks.
        max_blocks: Maximum number of blocks (default 50).

    Returns:
        Truncated blocks list with indicator if needed.
    """
    if len(blocks) <= max_blocks:
        return blocks
    # Leave room for truncation indicator
    truncated = blocks[: max_blocks - 1]
    truncated.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "... [truncated]"},
        }
    )
    return truncated


class SlackPublisher:
    """Publisher for sending messages via Slack Web API.

    Uses slack-sdk library for async Slack API communication.
    Handles validation, sending, updating, and retrying messages.
    """

    def __init__(self, token: str | None = None) -> None:
        """Initialize the publisher.

        Args:
            token: Slack Bot User OAuth Token (xoxb-...).
        """
        self._token = token
        self._client: object | None = None  # AsyncWebClient when available
        self._validated = False

    async def validate(self) -> None:
        """Validate bot credentials by calling auth_test.

        Raises:
            ValueError: If token not configured.
            SlackAuthError: If token invalid or bot unauthorized.
            SlackError: If slack-sdk is not installed.
        """
        if not self._token:
            raise ValueError("Slack bot token not configured")

        if self._validated:
            return

        if not check_slack_available():
            raise SlackError(
                "slack-sdk library not installed. Install with: pip install slack-sdk"
            )

        try:
            from slack_sdk.web.async_client import AsyncWebClient
            from slack_sdk.errors import SlackApiError

            self._client = AsyncWebClient(token=self._token)
            response = await self._client.auth_test()
            if not response["ok"]:
                raise SlackAuthError(
                    f"Auth test failed: {response.get('error', 'unknown error')}"
                )
            logger.info(
                f"Slack bot validated: {response.get('user', 'unknown')} "
                f"in {response.get('team', 'unknown')}"
            )
            self._validated = True
        except SlackApiError as e:
            raise SlackAuthError(f"Bot validation failed: {e}") from e

    async def send_message(
        self,
        channel: str,
        text: str,
        blocks: list[dict] | None = None,
    ) -> str:
        """Post a new message to a channel.

        Args:
            channel: Channel ID or name.
            text: Fallback text for notifications.
            blocks: Block Kit blocks (optional, preferred).

        Returns:
            message timestamp (ts) for future updates.

        Raises:
            SlackError: On API failure after retry.
        """
        if not self._validated:
            await self.validate()

        # Enforce block limit
        if blocks:
            blocks = _truncate_blocks(blocks)

        from slack_sdk.errors import SlackApiError

        try:
            response = await self._client.chat_postMessage(
                channel=channel,
                text=text,
                blocks=blocks,
            )
            return response["ts"]
        except SlackApiError:
            # Retry once after a short delay
            await asyncio.sleep(1)
            try:
                response = await self._client.chat_postMessage(
                    channel=channel,
                    text=text,
                    blocks=blocks,
                )
                return response["ts"]
            except SlackApiError as e2:
                logger.warning(f"Failed to post Slack message to {channel}: {e2}")
                raise SlackError(f"Post failed: {e2}") from e2

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict] | None = None,
    ) -> bool:
        """Update an existing message.

        Args:
            channel: Channel ID or name.
            ts: Message timestamp to update.
            text: Fallback text for notifications.
            blocks: Block Kit blocks (optional, preferred).

        Returns:
            True if updated successfully, False if message not found.
        """
        if not self._validated:
            await self.validate()

        # Enforce block limit
        if blocks:
            blocks = _truncate_blocks(blocks)

        from slack_sdk.errors import SlackApiError

        try:
            await self._client.chat_update(
                channel=channel,
                ts=ts,
                text=text,
                blocks=blocks,
            )
            return True
        except SlackApiError as e:
            error_str = str(e).lower()
            if "message_not_found" in error_str:
                return False

            # Retry once for other errors
            await asyncio.sleep(1)
            try:
                await self._client.chat_update(
                    channel=channel,
                    ts=ts,
                    text=text,
                    blocks=blocks,
                )
                return True
            except SlackApiError as e2:
                logger.warning(f"Failed to update Slack message {ts}: {e2}")
                return False

    async def close(self) -> None:
        """Close the client session."""
        if self._client is not None:
            # AsyncWebClient manages its own aiohttp session
            # When close() is called, we need to close the underlying session
            if hasattr(self._client, "_event_loop_thread_pool"):
                # Clean up thread pool if it exists
                pass
            self._client = None
            self._validated = False
