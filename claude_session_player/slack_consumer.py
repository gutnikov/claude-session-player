"""Slack consumer for posting session events to Slack channels.

This module provides the SlackConsumer class that posts and updates messages
in a Slack channel or thread as events arrive from the session processor.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient

from .events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    DurationContent,
    Event,
    QuestionContent,
    SystemContent,
    ThinkingContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from .formatter import format_duration

logger = logging.getLogger(__name__)

# Slack message character limit
SLACK_MESSAGE_LIMIT = 4000


class SlackConsumer:
    """Consumer that posts events to Slack.

    This consumer implements the Consumer protocol from protocol.py.
    It posts new messages for AddBlock events and updates existing messages
    for UpdateBlock events.

    Attributes:
        channel: Slack channel ID to post to.
        thread_ts: Optional thread timestamp to post in a thread.
    """

    def __init__(
        self,
        client: AsyncWebClient,
        channel: str,
        thread_ts: str | None = None,
    ) -> None:
        """Initialize the Slack consumer.

        Args:
            client: An initialized AsyncWebClient instance.
            channel: Slack channel ID to post messages to.
            thread_ts: Optional thread timestamp to post messages in a thread.
        """
        self._client = client
        self._channel = channel
        self._thread_ts = thread_ts
        self._block_to_message_ts: dict[str, str] = {}
        self._retry_delay = 1.0  # seconds between retries

    @classmethod
    def from_env(
        cls,
        channel: str,
        thread_ts: str | None = None,
    ) -> SlackConsumer:
        """Create a SlackConsumer with token from environment.

        Args:
            channel: Slack channel ID to post messages to.
            thread_ts: Optional thread timestamp to post messages in a thread.

        Returns:
            A configured SlackConsumer instance.

        Raises:
            ValueError: If SLACK_BOT_TOKEN is not set in environment.
        """
        from slack_sdk.web.async_client import AsyncWebClient

        token = os.environ.get("SLACK_BOT_TOKEN")
        if not token:
            raise ValueError("SLACK_BOT_TOKEN environment variable is not set")

        client = AsyncWebClient(token=token)
        return cls(client=client, channel=channel, thread_ts=thread_ts)

    async def on_event(self, event: Event) -> None:
        """Process a single event.

        AddBlock events post a new message to Slack.
        UpdateBlock events update an existing message.
        ClearAll events are ignored.

        Args:
            event: The event to process (AddBlock, UpdateBlock, or ClearAll).
        """
        if isinstance(event, AddBlock):
            await self._handle_add_block(event)
        elif isinstance(event, UpdateBlock):
            await self._handle_update_block(event)
        elif isinstance(event, ClearAll):
            # ClearAll is ignored - we don't delete messages from Slack
            logger.debug(
                "clear_all_ignored",
                extra={"reason": "slack_consumer_does_not_delete_messages"},
            )

    async def _handle_add_block(self, event: AddBlock) -> None:
        """Handle AddBlock event by posting a new message.

        Args:
            event: The AddBlock event containing the block to post.
        """
        block = event.block
        text = self.render_block(block)

        if not text:
            logger.debug(
                "add_block_skipped",
                extra={"block_id": block.id, "reason": "empty_render"},
            )
            return

        message_ts = await self._post_message_with_retry(text, block.id)
        if message_ts:
            self._block_to_message_ts[block.id] = message_ts
            logger.debug(
                "block_posted",
                extra={
                    "block_id": block.id,
                    "message_ts": message_ts,
                    "channel": self._channel,
                },
            )

    async def _handle_update_block(self, event: UpdateBlock) -> None:
        """Handle UpdateBlock event by updating an existing message.

        If the block_id is not found, the update is skipped silently.

        Args:
            event: The UpdateBlock event containing the update.
        """
        block_id = event.block_id
        message_ts = self._block_to_message_ts.get(block_id)

        if not message_ts:
            logger.debug(
                "update_block_skipped",
                extra={"block_id": block_id, "reason": "unknown_block_id"},
            )
            return

        # Create a temporary block to render the updated content
        # We need to determine the block type from the content
        block_type = self._content_to_block_type(event.content)
        temp_block = Block(
            id=block_id,
            type=block_type,
            content=event.content,
        )
        text = self.render_block(temp_block)

        if not text:
            logger.debug(
                "update_block_skipped",
                extra={"block_id": block_id, "reason": "empty_render"},
            )
            return

        success = await self._update_message_with_retry(text, message_ts, block_id)
        if success:
            logger.debug(
                "block_updated",
                extra={
                    "block_id": block_id,
                    "message_ts": message_ts,
                    "channel": self._channel,
                },
            )

    def _content_to_block_type(self, content) -> BlockType:
        """Determine block type from content.

        Args:
            content: The block content.

        Returns:
            The corresponding BlockType.
        """
        if isinstance(content, UserContent):
            return BlockType.USER
        elif isinstance(content, AssistantContent):
            return BlockType.ASSISTANT
        elif isinstance(content, ToolCallContent):
            return BlockType.TOOL_CALL
        elif isinstance(content, QuestionContent):
            return BlockType.QUESTION
        elif isinstance(content, ThinkingContent):
            return BlockType.THINKING
        elif isinstance(content, DurationContent):
            return BlockType.DURATION
        elif isinstance(content, SystemContent):
            return BlockType.SYSTEM
        else:
            return BlockType.SYSTEM

    async def _post_message_with_retry(
        self, text: str, block_id: str
    ) -> str | None:
        """Post a message to Slack with retry logic.

        Retries once on failure, then skips.

        Args:
            text: The message text to post.
            block_id: The block ID for logging.

        Returns:
            The message timestamp if successful, None if failed.
        """
        for attempt in range(2):  # Initial attempt + 1 retry
            try:
                response = await self._client.chat_postMessage(
                    channel=self._channel,
                    text=text,
                    thread_ts=self._thread_ts,
                )
                return response["ts"]
            except Exception as e:
                if attempt == 0:
                    logger.warning(
                        "post_message_retry",
                        extra={
                            "block_id": block_id,
                            "channel": self._channel,
                            "error": str(e),
                            "attempt": attempt + 1,
                        },
                    )
                    await asyncio.sleep(self._retry_delay)
                else:
                    logger.error(
                        "post_message_failed",
                        extra={
                            "block_id": block_id,
                            "channel": self._channel,
                            "error": str(e),
                            "attempts": attempt + 1,
                        },
                    )
        return None

    async def _update_message_with_retry(
        self, text: str, message_ts: str, block_id: str
    ) -> bool:
        """Update a Slack message with retry logic.

        Retries once on failure, then skips.

        Args:
            text: The updated message text.
            message_ts: The timestamp of the message to update.
            block_id: The block ID for logging.

        Returns:
            True if successful, False if failed.
        """
        for attempt in range(2):  # Initial attempt + 1 retry
            try:
                await self._client.chat_update(
                    channel=self._channel,
                    ts=message_ts,
                    text=text,
                )
                return True
            except Exception as e:
                if attempt == 0:
                    logger.warning(
                        "update_message_retry",
                        extra={
                            "block_id": block_id,
                            "message_ts": message_ts,
                            "channel": self._channel,
                            "error": str(e),
                            "attempt": attempt + 1,
                        },
                    )
                    await asyncio.sleep(self._retry_delay)
                else:
                    logger.error(
                        "update_message_failed",
                        extra={
                            "block_id": block_id,
                            "message_ts": message_ts,
                            "channel": self._channel,
                            "error": str(e),
                            "attempts": attempt + 1,
                        },
                    )
        return False

    def render_block(self, block: Block) -> str:
        """Render a block to its Slack message representation.

        Respects Slack's 4000 character message limit by truncating if needed.

        Args:
            block: The block to render.

        Returns:
            Slack-formatted string representation of the block.
        """
        text = self._render_block_content(block)
        return self._truncate_to_limit(text)

    def _render_block_content(self, block: Block) -> str:
        """Render block content without truncation.

        Args:
            block: The block to render.

        Returns:
            String representation of the block.
        """
        content = block.content

        if isinstance(content, UserContent):
            return self._render_user(content)
        elif isinstance(content, AssistantContent):
            return self._render_assistant(content)
        elif isinstance(content, ToolCallContent):
            return self._render_tool_call(content)
        elif isinstance(content, QuestionContent):
            return self._render_question(content)
        elif isinstance(content, ThinkingContent):
            return ":brain: _Thinking..._"
        elif isinstance(content, DurationContent):
            return f":stopwatch: Crunched for {format_duration(content.duration_ms)}"
        elif isinstance(content, SystemContent):
            return f"```\n{content.text}\n```"

        return ""

    def _render_user(self, content: UserContent) -> str:
        """Render user content for Slack.

        Args:
            content: The user content.

        Returns:
            Formatted user message.
        """
        return f":bust_in_silhouette: *User:*\n{content.text}"

    def _render_assistant(self, content: AssistantContent) -> str:
        """Render assistant content for Slack.

        Args:
            content: The assistant content.

        Returns:
            Formatted assistant message.
        """
        return f":robot_face: *Claude:*\n{content.text}"

    def _render_tool_call(self, content: ToolCallContent) -> str:
        """Render tool call content for Slack.

        Args:
            content: The tool call content.

        Returns:
            Formatted tool call message.
        """
        lines = [f":wrench: `{content.tool_name}({content.label})`"]

        if content.result is not None:
            prefix = ":x:" if content.is_error else ":white_check_mark:"
            lines.append(f"{prefix} Result:")
            lines.append(f"```\n{content.result}\n```")
        elif content.progress_text is not None:
            lines.append(f":hourglass: {content.progress_text}")

        return "\n".join(lines)

    def _render_question(self, content: QuestionContent) -> str:
        """Render question content for Slack.

        Args:
            content: The question content.

        Returns:
            Formatted question message.
        """
        parts: list[str] = []

        for question in content.questions:
            header = question.header or "Question"
            lines = [f":question: *{header}*", question.question]

            answer = None
            if content.answers:
                answer = content.answers.get(question.question)

            if answer:
                lines.append(f":white_check_mark: Selected: _{answer}_")
            else:
                for opt in question.options:
                    lines.append(f"  - {opt.label}")
                lines.append("_(awaiting response)_")

            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    def _truncate_to_limit(self, text: str) -> str:
        """Truncate text to Slack's message limit.

        Args:
            text: The text to truncate.

        Returns:
            Truncated text with ellipsis if needed.
        """
        if len(text) <= SLACK_MESSAGE_LIMIT:
            return text

        # Leave room for truncation indicator
        truncation_indicator = "\n... (truncated)"
        max_length = SLACK_MESSAGE_LIMIT - len(truncation_indicator)
        return text[:max_length] + truncation_indicator
