"""Telegram consumer for posting session events to Telegram chats.

This module provides the TelegramConsumer class that posts and updates messages
in a Telegram chat or thread as events arrive from the session processor.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Bot

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

# Telegram message character limit
TELEGRAM_MESSAGE_LIMIT = 4096


class TelegramConsumer:
    """Consumer that posts events to Telegram.

    This consumer implements the Consumer protocol from protocol.py.
    It posts new messages for AddBlock events and updates existing messages
    for UpdateBlock events.

    Attributes:
        chat_id: Telegram chat ID to post to.
        message_thread_id: Optional message thread ID to post in a topic/thread.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int | str,
        message_thread_id: int | None = None,
    ) -> None:
        """Initialize the Telegram consumer.

        Args:
            bot: An initialized telegram.Bot instance.
            chat_id: Telegram chat ID to post messages to.
            message_thread_id: Optional message thread ID to post messages in a topic.
        """
        self._bot = bot
        self._chat_id = chat_id
        self._message_thread_id = message_thread_id
        self._block_to_message_id: dict[str, int] = {}
        self._retry_delay = 1.0  # seconds between retries

    @classmethod
    def from_env(
        cls,
        chat_id: int | str,
        message_thread_id: int | None = None,
    ) -> TelegramConsumer:
        """Create a TelegramConsumer with token from environment.

        Args:
            chat_id: Telegram chat ID to post messages to.
            message_thread_id: Optional message thread ID to post messages in a topic.

        Returns:
            A configured TelegramConsumer instance.

        Raises:
            ValueError: If TELEGRAM_BOT_TOKEN is not set in environment.
        """
        from telegram import Bot

        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

        bot = Bot(token=token)
        return cls(bot=bot, chat_id=chat_id, message_thread_id=message_thread_id)

    async def on_event(self, event: Event) -> None:
        """Process a single event.

        AddBlock events post a new message to Telegram.
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
            # ClearAll is ignored - we don't delete messages from Telegram
            logger.debug(
                "clear_all_ignored",
                extra={"reason": "telegram_consumer_does_not_delete_messages"},
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

        message_id = await self._send_message_with_retry(text, block.id)
        if message_id:
            self._block_to_message_id[block.id] = message_id
            logger.debug(
                "block_posted",
                extra={
                    "block_id": block.id,
                    "message_id": message_id,
                    "chat_id": self._chat_id,
                },
            )

    async def _handle_update_block(self, event: UpdateBlock) -> None:
        """Handle UpdateBlock event by updating an existing message.

        If the block_id is not found, the update is skipped silently.

        Args:
            event: The UpdateBlock event containing the update.
        """
        block_id = event.block_id
        message_id = self._block_to_message_id.get(block_id)

        if not message_id:
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

        success = await self._edit_message_with_retry(text, message_id, block_id)
        if success:
            logger.debug(
                "block_updated",
                extra={
                    "block_id": block_id,
                    "message_id": message_id,
                    "chat_id": self._chat_id,
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

    async def _send_message_with_retry(
        self, text: str, block_id: str
    ) -> int | None:
        """Send a message to Telegram with retry logic.

        Retries once on failure, then skips.

        Args:
            text: The message text to send.
            block_id: The block ID for logging.

        Returns:
            The message ID if successful, None if failed.
        """
        for attempt in range(2):  # Initial attempt + 1 retry
            try:
                message = await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=text,
                    message_thread_id=self._message_thread_id,
                )
                return message.message_id
            except Exception as e:
                if attempt == 0:
                    logger.warning(
                        "send_message_retry",
                        extra={
                            "block_id": block_id,
                            "chat_id": self._chat_id,
                            "error": str(e),
                            "attempt": attempt + 1,
                        },
                    )
                    await asyncio.sleep(self._retry_delay)
                else:
                    logger.error(
                        "send_message_failed",
                        extra={
                            "block_id": block_id,
                            "chat_id": self._chat_id,
                            "error": str(e),
                            "attempts": attempt + 1,
                        },
                    )
        return None

    async def _edit_message_with_retry(
        self, text: str, message_id: int, block_id: str
    ) -> bool:
        """Edit a Telegram message with retry logic.

        Retries once on failure, then skips.

        Args:
            text: The updated message text.
            message_id: The ID of the message to edit.
            block_id: The block ID for logging.

        Returns:
            True if successful, False if failed.
        """
        for attempt in range(2):  # Initial attempt + 1 retry
            try:
                await self._bot.edit_message_text(
                    chat_id=self._chat_id,
                    message_id=message_id,
                    text=text,
                )
                return True
            except Exception as e:
                if attempt == 0:
                    logger.warning(
                        "edit_message_retry",
                        extra={
                            "block_id": block_id,
                            "message_id": message_id,
                            "chat_id": self._chat_id,
                            "error": str(e),
                            "attempt": attempt + 1,
                        },
                    )
                    await asyncio.sleep(self._retry_delay)
                else:
                    logger.error(
                        "edit_message_failed",
                        extra={
                            "block_id": block_id,
                            "message_id": message_id,
                            "chat_id": self._chat_id,
                            "error": str(e),
                            "attempts": attempt + 1,
                        },
                    )
        return False

    def render_block(self, block: Block) -> str:
        """Render a block to its Telegram message representation.

        Respects Telegram's 4096 character message limit by truncating if needed.

        Args:
            block: The block to render.

        Returns:
            Telegram-formatted string representation of the block.
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
            return "Thinking..."
        elif isinstance(content, DurationContent):
            return f"Crunched for {format_duration(content.duration_ms)}"
        elif isinstance(content, SystemContent):
            return f"```\n{content.text}\n```"

        return ""

    def _render_user(self, content: UserContent) -> str:
        """Render user content for Telegram.

        Args:
            content: The user content.

        Returns:
            Formatted user message.
        """
        return f"User:\n{content.text}"

    def _render_assistant(self, content: AssistantContent) -> str:
        """Render assistant content for Telegram.

        Args:
            content: The assistant content.

        Returns:
            Formatted assistant message.
        """
        return f"Claude:\n{content.text}"

    def _render_tool_call(self, content: ToolCallContent) -> str:
        """Render tool call content for Telegram.

        Args:
            content: The tool call content.

        Returns:
            Formatted tool call message.
        """
        lines = [f"{content.tool_name}({content.label})"]

        if content.result is not None:
            prefix = "[ERROR]" if content.is_error else "[OK]"
            lines.append(f"{prefix} Result:")
            lines.append(f"```\n{content.result}\n```")
        elif content.progress_text is not None:
            lines.append(f"[...] {content.progress_text}")

        return "\n".join(lines)

    def _render_question(self, content: QuestionContent) -> str:
        """Render question content for Telegram.

        Args:
            content: The question content.

        Returns:
            Formatted question message.
        """
        parts: list[str] = []

        for question in content.questions:
            header = question.header or "Question"
            lines = [f"[?] {header}", question.question]

            answer = None
            if content.answers:
                answer = content.answers.get(question.question)

            if answer:
                lines.append(f"[OK] Selected: {answer}")
            else:
                for opt in question.options:
                    lines.append(f"  - {opt.label}")
                lines.append("(awaiting response)")

            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    def _truncate_to_limit(self, text: str) -> str:
        """Truncate text to Telegram's message limit.

        Args:
            text: The text to truncate.

        Returns:
            Truncated text with ellipsis if needed.
        """
        if len(text) <= TELEGRAM_MESSAGE_LIMIT:
            return text

        # Leave room for truncation indicator
        truncation_indicator = "\n... (truncated)"
        max_length = TELEGRAM_MESSAGE_LIMIT - len(truncation_indicator)
        return text[:max_length] + truncation_indicator
