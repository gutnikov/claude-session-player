"""Tests for the TelegramConsumer class."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    DurationContent,
    Event,
    Question,
    QuestionContent,
    QuestionOption,
    SystemContent,
    ThinkingContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from claude_session_player.protocol import Consumer
from claude_session_player.telegram_consumer import (
    TELEGRAM_MESSAGE_LIMIT,
    TelegramConsumer,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot() -> AsyncMock:
    """Create a mock Telegram Bot."""
    bot = AsyncMock()
    mock_message = MagicMock()
    mock_message.message_id = 12345
    bot.send_message = AsyncMock(return_value=mock_message)
    bot.edit_message_text = AsyncMock(return_value=True)
    return bot


@pytest.fixture
def consumer(mock_bot: AsyncMock) -> TelegramConsumer:
    """Create a TelegramConsumer with mocked bot."""
    c = TelegramConsumer(
        bot=mock_bot,
        chat_id=123456789,
        message_thread_id=None,
    )
    # Set retry delay to 0 for faster tests
    c._retry_delay = 0
    return c


@pytest.fixture
def consumer_with_thread(mock_bot: AsyncMock) -> TelegramConsumer:
    """Create a TelegramConsumer with message_thread_id."""
    c = TelegramConsumer(
        bot=mock_bot,
        chat_id=123456789,
        message_thread_id=42,
    )
    c._retry_delay = 0
    return c


@pytest.fixture
def user_block() -> Block:
    """Create a sample user block."""
    return Block(
        id="block-user-1",
        type=BlockType.USER,
        content=UserContent(text="Hello"),
    )


@pytest.fixture
def assistant_block() -> Block:
    """Create a sample assistant block."""
    return Block(
        id="block-assistant-1",
        type=BlockType.ASSISTANT,
        content=AssistantContent(text="Hi there"),
        request_id="req-123",
    )


@pytest.fixture
def tool_call_block() -> Block:
    """Create a sample tool call block."""
    return Block(
        id="block-tool-1",
        type=BlockType.TOOL_CALL,
        content=ToolCallContent(
            tool_name="Read",
            tool_use_id="tool-1",
            label="file.txt",
        ),
    )


# ---------------------------------------------------------------------------
# Test Consumer protocol compliance
# ---------------------------------------------------------------------------


class TestConsumerProtocol:
    """Tests for Consumer protocol compliance."""

    def test_telegram_consumer_is_consumer(self, consumer: TelegramConsumer) -> None:
        """TelegramConsumer implements Consumer protocol."""
        assert isinstance(consumer, Consumer)

    def test_has_on_event_method(self, consumer: TelegramConsumer) -> None:
        """TelegramConsumer has on_event method."""
        assert hasattr(consumer, "on_event")
        assert callable(consumer.on_event)

    def test_has_render_block_method(self, consumer: TelegramConsumer) -> None:
        """TelegramConsumer has render_block method."""
        assert hasattr(consumer, "render_block")
        assert callable(consumer.render_block)


# ---------------------------------------------------------------------------
# Test AddBlock event handling
# ---------------------------------------------------------------------------


class TestAddBlock:
    """Tests for AddBlock event handling."""

    @pytest.mark.asyncio
    async def test_add_block_sends_message(
        self, consumer: TelegramConsumer, mock_bot: AsyncMock, user_block: Block
    ) -> None:
        """AddBlock sends a message to Telegram."""
        event = AddBlock(block=user_block)

        await consumer.on_event(event)

        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 123456789
        assert "Hello" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_add_block_stores_message_id(
        self, consumer: TelegramConsumer, mock_bot: AsyncMock, user_block: Block
    ) -> None:
        """AddBlock stores the message ID for later updates."""
        event = AddBlock(block=user_block)

        await consumer.on_event(event)

        assert user_block.id in consumer._block_to_message_id
        assert consumer._block_to_message_id[user_block.id] == 12345

    @pytest.mark.asyncio
    async def test_add_block_with_thread_id(
        self,
        consumer_with_thread: TelegramConsumer,
        mock_bot: AsyncMock,
        user_block: Block,
    ) -> None:
        """AddBlock sends to thread when message_thread_id is set."""
        event = AddBlock(block=user_block)

        await consumer_with_thread.on_event(event)

        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["message_thread_id"] == 42

    @pytest.mark.asyncio
    async def test_add_block_without_thread_id(
        self, consumer: TelegramConsumer, mock_bot: AsyncMock, user_block: Block
    ) -> None:
        """AddBlock sends without message_thread_id when not set."""
        event = AddBlock(block=user_block)

        await consumer.on_event(event)

        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["message_thread_id"] is None


# ---------------------------------------------------------------------------
# Test UpdateBlock event handling
# ---------------------------------------------------------------------------


class TestUpdateBlock:
    """Tests for UpdateBlock event handling."""

    @pytest.mark.asyncio
    async def test_update_block_edits_message(
        self,
        consumer: TelegramConsumer,
        mock_bot: AsyncMock,
        tool_call_block: Block,
    ) -> None:
        """UpdateBlock edits an existing message."""
        # First add the block
        await consumer.on_event(AddBlock(block=tool_call_block))

        # Then update it
        updated_content = ToolCallContent(
            tool_name="Read",
            tool_use_id="tool-1",
            label="file.txt",
            result="File contents here",
        )
        update_event = UpdateBlock(
            block_id=tool_call_block.id,
            content=updated_content,
        )

        await consumer.on_event(update_event)

        mock_bot.edit_message_text.assert_called_once()
        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        assert call_kwargs["chat_id"] == 123456789
        assert call_kwargs["message_id"] == 12345
        assert "File contents here" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_update_block_unknown_id_skipped(
        self,
        consumer: TelegramConsumer,
        mock_bot: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """UpdateBlock for unknown block_id is skipped silently."""
        update_event = UpdateBlock(
            block_id="unknown-block-id",
            content=AssistantContent(text="Updated text"),
        )

        with caplog.at_level(logging.DEBUG):
            await consumer.on_event(update_event)

        mock_bot.edit_message_text.assert_not_called()
        assert "update_block_skipped" in caplog.text


# ---------------------------------------------------------------------------
# Test ClearAll event handling
# ---------------------------------------------------------------------------


class TestClearAll:
    """Tests for ClearAll event handling."""

    @pytest.mark.asyncio
    async def test_clear_all_ignored(
        self,
        consumer: TelegramConsumer,
        mock_bot: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """ClearAll event is ignored (no action)."""
        event = ClearAll()

        with caplog.at_level(logging.DEBUG):
            await consumer.on_event(event)

        # No Telegram API calls should be made
        mock_bot.send_message.assert_not_called()
        mock_bot.edit_message_text.assert_not_called()
        assert "clear_all_ignored" in caplog.text


# ---------------------------------------------------------------------------
# Test retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """Tests for retry logic on API failures."""

    @pytest.mark.asyncio
    async def test_send_message_retries_once(
        self,
        consumer: TelegramConsumer,
        mock_bot: AsyncMock,
        user_block: Block,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """send_message retries once on failure."""
        # First call fails, second succeeds
        mock_message = MagicMock()
        mock_message.message_id = 12345
        mock_bot.send_message.side_effect = [
            Exception("Network error"),
            mock_message,
        ]
        event = AddBlock(block=user_block)

        with caplog.at_level(logging.WARNING):
            await consumer.on_event(event)

        assert mock_bot.send_message.call_count == 2
        assert "send_message_retry" in caplog.text
        assert user_block.id in consumer._block_to_message_id

    @pytest.mark.asyncio
    async def test_send_message_fails_after_retry(
        self,
        consumer: TelegramConsumer,
        mock_bot: AsyncMock,
        user_block: Block,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """send_message skips after retry fails."""
        # Both calls fail
        mock_bot.send_message.side_effect = Exception("Network error")
        event = AddBlock(block=user_block)

        with caplog.at_level(logging.ERROR):
            await consumer.on_event(event)

        assert mock_bot.send_message.call_count == 2
        assert "send_message_failed" in caplog.text
        assert user_block.id not in consumer._block_to_message_id

    @pytest.mark.asyncio
    async def test_edit_message_retries_once(
        self,
        consumer: TelegramConsumer,
        mock_bot: AsyncMock,
        tool_call_block: Block,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """edit_message retries once on failure."""
        # Add block first
        await consumer.on_event(AddBlock(block=tool_call_block))

        # First edit call fails, second succeeds
        mock_bot.edit_message_text.side_effect = [
            Exception("Network error"),
            True,
        ]
        update_event = UpdateBlock(
            block_id=tool_call_block.id,
            content=ToolCallContent(
                tool_name="Read",
                tool_use_id="tool-1",
                label="file.txt",
                result="Result",
            ),
        )

        with caplog.at_level(logging.WARNING):
            await consumer.on_event(update_event)

        assert mock_bot.edit_message_text.call_count == 2
        assert "edit_message_retry" in caplog.text

    @pytest.mark.asyncio
    async def test_edit_message_fails_after_retry(
        self,
        consumer: TelegramConsumer,
        mock_bot: AsyncMock,
        tool_call_block: Block,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """edit_message skips after retry fails."""
        # Add block first
        await consumer.on_event(AddBlock(block=tool_call_block))

        # Both edit calls fail
        mock_bot.edit_message_text.side_effect = Exception("Network error")
        update_event = UpdateBlock(
            block_id=tool_call_block.id,
            content=ToolCallContent(
                tool_name="Read",
                tool_use_id="tool-1",
                label="file.txt",
                result="Result",
            ),
        )

        with caplog.at_level(logging.ERROR):
            await consumer.on_event(update_event)

        assert mock_bot.edit_message_text.call_count == 2
        assert "edit_message_failed" in caplog.text


# ---------------------------------------------------------------------------
# Test render_block
# ---------------------------------------------------------------------------


class TestRenderBlock:
    """Tests for render_block method."""

    def test_render_user_content(self, consumer: TelegramConsumer) -> None:
        """render_block formats user content correctly."""
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello world"),
        )

        result = consumer.render_block(block)

        assert "User:" in result
        assert "Hello world" in result

    def test_render_assistant_content(self, consumer: TelegramConsumer) -> None:
        """render_block formats assistant content correctly."""
        block = Block(
            id="block-1",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="Hi there!"),
        )

        result = consumer.render_block(block)

        assert "Claude:" in result
        assert "Hi there!" in result

    def test_render_tool_call_without_result(self, consumer: TelegramConsumer) -> None:
        """render_block formats tool call without result."""
        block = Block(
            id="block-1",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Bash",
                tool_use_id="tool-1",
                label="ls -la",
            ),
        )

        result = consumer.render_block(block)

        assert "Bash(ls -la)" in result

    def test_render_tool_call_with_result(self, consumer: TelegramConsumer) -> None:
        """render_block formats tool call with result."""
        block = Block(
            id="block-1",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Read",
                tool_use_id="tool-1",
                label="file.txt",
                result="File contents",
            ),
        )

        result = consumer.render_block(block)

        assert "Read(file.txt)" in result
        assert "[OK]" in result
        assert "File contents" in result

    def test_render_tool_call_with_error(self, consumer: TelegramConsumer) -> None:
        """render_block formats tool call with error."""
        block = Block(
            id="block-1",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Bash",
                tool_use_id="tool-1",
                label="invalid_command",
                result="Command not found",
                is_error=True,
            ),
        )

        result = consumer.render_block(block)

        assert "[ERROR]" in result
        assert "Command not found" in result

    def test_render_tool_call_with_progress(self, consumer: TelegramConsumer) -> None:
        """render_block formats tool call with progress."""
        block = Block(
            id="block-1",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Bash",
                tool_use_id="tool-1",
                label="long_command",
                progress_text="Running...",
            ),
        )

        result = consumer.render_block(block)

        assert "[...]" in result
        assert "Running..." in result

    def test_render_thinking_content(self, consumer: TelegramConsumer) -> None:
        """render_block formats thinking content."""
        block = Block(
            id="block-1",
            type=BlockType.THINKING,
            content=ThinkingContent(),
        )

        result = consumer.render_block(block)

        assert "Thinking..." in result

    def test_render_duration_content(self, consumer: TelegramConsumer) -> None:
        """render_block formats duration content."""
        block = Block(
            id="block-1",
            type=BlockType.DURATION,
            content=DurationContent(duration_ms=65000),
        )

        result = consumer.render_block(block)

        assert "Crunched for" in result
        assert "1m 5s" in result

    def test_render_system_content(self, consumer: TelegramConsumer) -> None:
        """render_block formats system content."""
        block = Block(
            id="block-1",
            type=BlockType.SYSTEM,
            content=SystemContent(text="System message"),
        )

        result = consumer.render_block(block)

        assert "```" in result
        assert "System message" in result

    def test_render_question_content(self, consumer: TelegramConsumer) -> None:
        """render_block formats question content."""
        block = Block(
            id="block-1",
            type=BlockType.QUESTION,
            content=QuestionContent(
                tool_use_id="q-1",
                questions=[
                    Question(
                        question="Continue?",
                        header="Confirm",
                        options=[
                            QuestionOption(label="Yes", description="Continue"),
                            QuestionOption(label="No", description="Cancel"),
                        ],
                    )
                ],
            ),
        )

        result = consumer.render_block(block)

        assert "[?]" in result
        assert "Confirm" in result
        assert "Continue?" in result
        assert "- Yes" in result
        assert "- No" in result

    def test_render_question_with_answer(self, consumer: TelegramConsumer) -> None:
        """render_block formats answered question."""
        block = Block(
            id="block-1",
            type=BlockType.QUESTION,
            content=QuestionContent(
                tool_use_id="q-1",
                questions=[
                    Question(
                        question="Continue?",
                        header="Confirm",
                        options=[
                            QuestionOption(label="Yes", description="Continue"),
                            QuestionOption(label="No", description="Cancel"),
                        ],
                    )
                ],
                answers={"Continue?": "Yes"},
            ),
        )

        result = consumer.render_block(block)

        assert "[OK]" in result
        assert "Yes" in result


# ---------------------------------------------------------------------------
# Test 4096 character limit
# ---------------------------------------------------------------------------


class TestMessageLimit:
    """Tests for Telegram's 4096 character message limit."""

    def test_truncate_long_message(self, consumer: TelegramConsumer) -> None:
        """render_block truncates messages exceeding 4096 chars."""
        long_text = "x" * 5000
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text=long_text),
        )

        result = consumer.render_block(block)

        assert len(result) <= TELEGRAM_MESSAGE_LIMIT
        assert "... (truncated)" in result

    def test_short_message_not_truncated(self, consumer: TelegramConsumer) -> None:
        """render_block does not truncate short messages."""
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Short message"),
        )

        result = consumer.render_block(block)

        assert "... (truncated)" not in result

    def test_exactly_at_limit_not_truncated(self, consumer: TelegramConsumer) -> None:
        """Message exactly at limit is not truncated."""
        # Create a message that will render to exactly 4096 chars
        # Account for the formatting prefix
        prefix = "User:\n"
        text_length = TELEGRAM_MESSAGE_LIMIT - len(prefix)
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="x" * text_length),
        )

        result = consumer.render_block(block)

        assert len(result) == TELEGRAM_MESSAGE_LIMIT
        assert "... (truncated)" not in result


# ---------------------------------------------------------------------------
# Test from_env factory
# ---------------------------------------------------------------------------


class TestFromEnv:
    """Tests for from_env factory method."""

    def test_from_env_missing_token(self) -> None:
        """from_env raises ValueError if token not set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
                TelegramConsumer.from_env(chat_id=123456789)

    def test_from_env_with_token(self) -> None:
        """from_env creates consumer with token from environment."""
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "123456:ABC-test-token"}):
            with patch("telegram.Bot") as mock_bot_class:
                mock_bot_class.return_value = MagicMock()

                consumer = TelegramConsumer.from_env(
                    chat_id=123456789,
                    message_thread_id=42,
                )

                mock_bot_class.assert_called_once_with(token="123456:ABC-test-token")
                assert consumer._chat_id == 123456789
                assert consumer._message_thread_id == 42

    def test_from_env_with_string_chat_id(self) -> None:
        """from_env accepts string chat_id."""
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "123456:ABC-test-token"}):
            with patch("telegram.Bot") as mock_bot_class:
                mock_bot_class.return_value = MagicMock()

                consumer = TelegramConsumer.from_env(
                    chat_id="@channelname",
                )

                assert consumer._chat_id == "@channelname"


# ---------------------------------------------------------------------------
# Test multiple events
# ---------------------------------------------------------------------------


class TestMultipleEvents:
    """Tests for handling multiple events."""

    @pytest.mark.asyncio
    async def test_multiple_add_blocks(
        self, consumer: TelegramConsumer, mock_bot: AsyncMock
    ) -> None:
        """Multiple AddBlock events send multiple messages."""
        blocks = [
            Block(
                id=f"block-{i}",
                type=BlockType.USER,
                content=UserContent(text=f"Message {i}"),
            )
            for i in range(3)
        ]
        # Configure different message IDs for each response
        mock_messages = [MagicMock() for _ in range(3)]
        for i, msg in enumerate(mock_messages):
            msg.message_id = 12345 + i
        mock_bot.send_message.side_effect = mock_messages

        for block in blocks:
            await consumer.on_event(AddBlock(block=block))

        assert mock_bot.send_message.call_count == 3
        assert len(consumer._block_to_message_id) == 3

    @pytest.mark.asyncio
    async def test_add_then_update(
        self, consumer: TelegramConsumer, mock_bot: AsyncMock
    ) -> None:
        """Add followed by update works correctly."""
        block = Block(
            id="block-1",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Bash",
                tool_use_id="tool-1",
                label="command",
            ),
        )

        # Add the block
        await consumer.on_event(AddBlock(block=block))

        # Update the block
        await consumer.on_event(
            UpdateBlock(
                block_id="block-1",
                content=ToolCallContent(
                    tool_name="Bash",
                    tool_use_id="tool-1",
                    label="command",
                    result="Output",
                ),
            )
        )

        assert mock_bot.send_message.call_count == 1
        assert mock_bot.edit_message_text.call_count == 1
