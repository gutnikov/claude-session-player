"""Tests for the SlackConsumer class."""

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
from claude_session_player.slack_consumer import SLACK_MESSAGE_LIMIT, SlackConsumer


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> AsyncMock:
    """Create a mock Slack AsyncWebClient."""
    client = AsyncMock()
    client.chat_postMessage = AsyncMock(return_value={"ts": "1234567890.123456"})
    client.chat_update = AsyncMock(return_value={"ok": True})
    return client


@pytest.fixture
def consumer(mock_client: AsyncMock) -> SlackConsumer:
    """Create a SlackConsumer with mocked client."""
    c = SlackConsumer(
        client=mock_client,
        channel="C12345678",
        thread_ts=None,
    )
    # Set retry delay to 0 for faster tests
    c._retry_delay = 0
    return c


@pytest.fixture
def consumer_with_thread(mock_client: AsyncMock) -> SlackConsumer:
    """Create a SlackConsumer with thread_ts."""
    c = SlackConsumer(
        client=mock_client,
        channel="C12345678",
        thread_ts="1234567890.000000",
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

    def test_slack_consumer_is_consumer(self, consumer: SlackConsumer) -> None:
        """SlackConsumer implements Consumer protocol."""
        assert isinstance(consumer, Consumer)

    def test_has_on_event_method(self, consumer: SlackConsumer) -> None:
        """SlackConsumer has on_event method."""
        assert hasattr(consumer, "on_event")
        assert callable(consumer.on_event)

    def test_has_render_block_method(self, consumer: SlackConsumer) -> None:
        """SlackConsumer has render_block method."""
        assert hasattr(consumer, "render_block")
        assert callable(consumer.render_block)


# ---------------------------------------------------------------------------
# Test AddBlock event handling
# ---------------------------------------------------------------------------


class TestAddBlock:
    """Tests for AddBlock event handling."""

    @pytest.mark.asyncio
    async def test_add_block_posts_message(
        self, consumer: SlackConsumer, mock_client: AsyncMock, user_block: Block
    ) -> None:
        """AddBlock posts a message to Slack."""
        event = AddBlock(block=user_block)

        await consumer.on_event(event)

        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert call_kwargs["channel"] == "C12345678"
        assert "Hello" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_add_block_stores_message_ts(
        self, consumer: SlackConsumer, mock_client: AsyncMock, user_block: Block
    ) -> None:
        """AddBlock stores the message timestamp for later updates."""
        event = AddBlock(block=user_block)

        await consumer.on_event(event)

        assert user_block.id in consumer._block_to_message_ts
        assert consumer._block_to_message_ts[user_block.id] == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_add_block_with_thread_ts(
        self,
        consumer_with_thread: SlackConsumer,
        mock_client: AsyncMock,
        user_block: Block,
    ) -> None:
        """AddBlock posts to thread when thread_ts is set."""
        event = AddBlock(block=user_block)

        await consumer_with_thread.on_event(event)

        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert call_kwargs["thread_ts"] == "1234567890.000000"

    @pytest.mark.asyncio
    async def test_add_block_without_thread_ts(
        self, consumer: SlackConsumer, mock_client: AsyncMock, user_block: Block
    ) -> None:
        """AddBlock posts without thread_ts when not set."""
        event = AddBlock(block=user_block)

        await consumer.on_event(event)

        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert call_kwargs["thread_ts"] is None


# ---------------------------------------------------------------------------
# Test UpdateBlock event handling
# ---------------------------------------------------------------------------


class TestUpdateBlock:
    """Tests for UpdateBlock event handling."""

    @pytest.mark.asyncio
    async def test_update_block_updates_message(
        self,
        consumer: SlackConsumer,
        mock_client: AsyncMock,
        tool_call_block: Block,
    ) -> None:
        """UpdateBlock updates an existing message."""
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

        mock_client.chat_update.assert_called_once()
        call_kwargs = mock_client.chat_update.call_args.kwargs
        assert call_kwargs["channel"] == "C12345678"
        assert call_kwargs["ts"] == "1234567890.123456"
        assert "File contents here" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_update_block_unknown_id_skipped(
        self,
        consumer: SlackConsumer,
        mock_client: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """UpdateBlock for unknown block_id is skipped silently."""
        update_event = UpdateBlock(
            block_id="unknown-block-id",
            content=AssistantContent(text="Updated text"),
        )

        with caplog.at_level(logging.DEBUG):
            await consumer.on_event(update_event)

        mock_client.chat_update.assert_not_called()
        assert "update_block_skipped" in caplog.text


# ---------------------------------------------------------------------------
# Test ClearAll event handling
# ---------------------------------------------------------------------------


class TestClearAll:
    """Tests for ClearAll event handling."""

    @pytest.mark.asyncio
    async def test_clear_all_ignored(
        self,
        consumer: SlackConsumer,
        mock_client: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """ClearAll event is ignored (no action)."""
        event = ClearAll()

        with caplog.at_level(logging.DEBUG):
            await consumer.on_event(event)

        # No Slack API calls should be made
        mock_client.chat_postMessage.assert_not_called()
        mock_client.chat_update.assert_not_called()
        assert "clear_all_ignored" in caplog.text


# ---------------------------------------------------------------------------
# Test retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """Tests for retry logic on API failures."""

    @pytest.mark.asyncio
    async def test_post_message_retries_once(
        self,
        consumer: SlackConsumer,
        mock_client: AsyncMock,
        user_block: Block,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """post_message retries once on failure."""
        # First call fails, second succeeds
        mock_client.chat_postMessage.side_effect = [
            Exception("Network error"),
            {"ts": "1234567890.123456"},
        ]
        event = AddBlock(block=user_block)

        with caplog.at_level(logging.WARNING):
            await consumer.on_event(event)

        assert mock_client.chat_postMessage.call_count == 2
        assert "post_message_retry" in caplog.text
        assert user_block.id in consumer._block_to_message_ts

    @pytest.mark.asyncio
    async def test_post_message_fails_after_retry(
        self,
        consumer: SlackConsumer,
        mock_client: AsyncMock,
        user_block: Block,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """post_message skips after retry fails."""
        # Both calls fail
        mock_client.chat_postMessage.side_effect = Exception("Network error")
        event = AddBlock(block=user_block)

        with caplog.at_level(logging.ERROR):
            await consumer.on_event(event)

        assert mock_client.chat_postMessage.call_count == 2
        assert "post_message_failed" in caplog.text
        assert user_block.id not in consumer._block_to_message_ts

    @pytest.mark.asyncio
    async def test_update_message_retries_once(
        self,
        consumer: SlackConsumer,
        mock_client: AsyncMock,
        tool_call_block: Block,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """update_message retries once on failure."""
        # Add block first
        await consumer.on_event(AddBlock(block=tool_call_block))

        # First update call fails, second succeeds
        mock_client.chat_update.side_effect = [
            Exception("Network error"),
            {"ok": True},
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

        assert mock_client.chat_update.call_count == 2
        assert "update_message_retry" in caplog.text

    @pytest.mark.asyncio
    async def test_update_message_fails_after_retry(
        self,
        consumer: SlackConsumer,
        mock_client: AsyncMock,
        tool_call_block: Block,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """update_message skips after retry fails."""
        # Add block first
        await consumer.on_event(AddBlock(block=tool_call_block))

        # Both update calls fail
        mock_client.chat_update.side_effect = Exception("Network error")
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

        assert mock_client.chat_update.call_count == 2
        assert "update_message_failed" in caplog.text


# ---------------------------------------------------------------------------
# Test render_block
# ---------------------------------------------------------------------------


class TestRenderBlock:
    """Tests for render_block method."""

    def test_render_user_content(self, consumer: SlackConsumer) -> None:
        """render_block formats user content correctly."""
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello world"),
        )

        result = consumer.render_block(block)

        assert ":bust_in_silhouette:" in result
        assert "*User:*" in result
        assert "Hello world" in result

    def test_render_assistant_content(self, consumer: SlackConsumer) -> None:
        """render_block formats assistant content correctly."""
        block = Block(
            id="block-1",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="Hi there!"),
        )

        result = consumer.render_block(block)

        assert ":robot_face:" in result
        assert "*Claude:*" in result
        assert "Hi there!" in result

    def test_render_tool_call_without_result(self, consumer: SlackConsumer) -> None:
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

        assert ":wrench:" in result
        assert "`Bash(ls -la)`" in result

    def test_render_tool_call_with_result(self, consumer: SlackConsumer) -> None:
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

        assert ":wrench:" in result
        assert ":white_check_mark:" in result
        assert "File contents" in result

    def test_render_tool_call_with_error(self, consumer: SlackConsumer) -> None:
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

        assert ":x:" in result
        assert "Command not found" in result

    def test_render_tool_call_with_progress(self, consumer: SlackConsumer) -> None:
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

        assert ":hourglass:" in result
        assert "Running..." in result

    def test_render_thinking_content(self, consumer: SlackConsumer) -> None:
        """render_block formats thinking content."""
        block = Block(
            id="block-1",
            type=BlockType.THINKING,
            content=ThinkingContent(),
        )

        result = consumer.render_block(block)

        assert ":brain:" in result
        assert "_Thinking..._" in result

    def test_render_duration_content(self, consumer: SlackConsumer) -> None:
        """render_block formats duration content."""
        block = Block(
            id="block-1",
            type=BlockType.DURATION,
            content=DurationContent(duration_ms=65000),
        )

        result = consumer.render_block(block)

        assert ":stopwatch:" in result
        assert "1m 5s" in result

    def test_render_system_content(self, consumer: SlackConsumer) -> None:
        """render_block formats system content."""
        block = Block(
            id="block-1",
            type=BlockType.SYSTEM,
            content=SystemContent(text="System message"),
        )

        result = consumer.render_block(block)

        assert "```" in result
        assert "System message" in result

    def test_render_question_content(self, consumer: SlackConsumer) -> None:
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

        assert ":question:" in result
        assert "*Confirm*" in result
        assert "Continue?" in result
        assert "- Yes" in result
        assert "- No" in result

    def test_render_question_with_answer(self, consumer: SlackConsumer) -> None:
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

        assert ":white_check_mark:" in result
        assert "_Yes_" in result


# ---------------------------------------------------------------------------
# Test 4000 character limit
# ---------------------------------------------------------------------------


class TestMessageLimit:
    """Tests for Slack's 4000 character message limit."""

    def test_truncate_long_message(self, consumer: SlackConsumer) -> None:
        """render_block truncates messages exceeding 4000 chars."""
        long_text = "x" * 5000
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text=long_text),
        )

        result = consumer.render_block(block)

        assert len(result) <= SLACK_MESSAGE_LIMIT
        assert "... (truncated)" in result

    def test_short_message_not_truncated(self, consumer: SlackConsumer) -> None:
        """render_block does not truncate short messages."""
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Short message"),
        )

        result = consumer.render_block(block)

        assert "... (truncated)" not in result

    def test_exactly_at_limit_not_truncated(self, consumer: SlackConsumer) -> None:
        """Message exactly at limit is not truncated."""
        # Create a message that will render to exactly 4000 chars
        # Account for the formatting prefix
        prefix = ":bust_in_silhouette: *User:*\n"
        text_length = SLACK_MESSAGE_LIMIT - len(prefix)
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="x" * text_length),
        )

        result = consumer.render_block(block)

        assert len(result) == SLACK_MESSAGE_LIMIT
        assert "... (truncated)" not in result


# ---------------------------------------------------------------------------
# Test from_env factory
# ---------------------------------------------------------------------------


class TestFromEnv:
    """Tests for from_env factory method."""

    def test_from_env_missing_token(self) -> None:
        """from_env raises ValueError if token not set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="SLACK_BOT_TOKEN"):
                SlackConsumer.from_env(channel="C12345678")

    def test_from_env_with_token(self) -> None:
        """from_env creates consumer with token from environment."""
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test-token"}):
            with patch(
                "slack_sdk.web.async_client.AsyncWebClient"
            ) as mock_client_class:
                mock_client_class.return_value = MagicMock()

                consumer = SlackConsumer.from_env(
                    channel="C12345678",
                    thread_ts="1234567890.000000",
                )

                mock_client_class.assert_called_once_with(token="xoxb-test-token")
                assert consumer._channel == "C12345678"
                assert consumer._thread_ts == "1234567890.000000"


# ---------------------------------------------------------------------------
# Test multiple events
# ---------------------------------------------------------------------------


class TestMultipleEvents:
    """Tests for handling multiple events."""

    @pytest.mark.asyncio
    async def test_multiple_add_blocks(
        self, consumer: SlackConsumer, mock_client: AsyncMock
    ) -> None:
        """Multiple AddBlock events post multiple messages."""
        blocks = [
            Block(id=f"block-{i}", type=BlockType.USER, content=UserContent(text=f"Message {i}"))
            for i in range(3)
        ]
        # Configure different timestamps for each response
        mock_client.chat_postMessage.side_effect = [
            {"ts": f"123456789{i}.000000"} for i in range(3)
        ]

        for block in blocks:
            await consumer.on_event(AddBlock(block=block))

        assert mock_client.chat_postMessage.call_count == 3
        assert len(consumer._block_to_message_ts) == 3

    @pytest.mark.asyncio
    async def test_add_then_update(
        self, consumer: SlackConsumer, mock_client: AsyncMock
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

        assert mock_client.chat_postMessage.call_count == 1
        assert mock_client.chat_update.call_count == 1
