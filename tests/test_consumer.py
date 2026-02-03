"""Tests for the ScreenStateConsumer and related formatting functions."""

from __future__ import annotations

import pytest

from claude_session_player.consumer import (
    ScreenStateConsumer,
    format_assistant_text,
    format_block,
    format_tool_call,
    format_user_text,
    replay_session,
)
from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    DurationContent,
    ProcessingContext,
    SystemContent,
    ThinkingContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def consumer() -> ScreenStateConsumer:
    """Create a fresh ScreenStateConsumer instance."""
    return ScreenStateConsumer()


@pytest.fixture
def user_block() -> Block:
    """Create a sample user block."""
    return Block(
        id="block-user-1",
        type=BlockType.USER,
        content=UserContent(text="Hello, Claude"),
    )


@pytest.fixture
def assistant_block() -> Block:
    """Create a sample assistant block."""
    return Block(
        id="block-assistant-1",
        type=BlockType.ASSISTANT,
        content=AssistantContent(text="Hello! How can I help you?"),
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
            tool_use_id="tool-use-1",
            label="README.md",
        ),
        request_id="req-123",
    )


# ---------------------------------------------------------------------------
# Test AddBlock event handling
# ---------------------------------------------------------------------------


class TestAddBlock:
    """Tests for AddBlock event handling."""

    def test_add_block_appends_to_blocks_list(
        self, consumer: ScreenStateConsumer, user_block: Block
    ) -> None:
        """AddBlock appends to blocks list."""
        consumer.handle(AddBlock(block=user_block))
        assert len(consumer.blocks) == 1
        assert consumer.blocks[0] is user_block

    def test_add_block_updates_block_index(
        self, consumer: ScreenStateConsumer, user_block: Block
    ) -> None:
        """AddBlock updates block_index."""
        consumer.handle(AddBlock(block=user_block))
        assert consumer._block_index["block-user-1"] == 0

    def test_multiple_add_blocks_in_sequence(
        self,
        consumer: ScreenStateConsumer,
        user_block: Block,
        assistant_block: Block,
        tool_call_block: Block,
    ) -> None:
        """Multiple AddBlock events in sequence."""
        consumer.handle(AddBlock(block=user_block))
        consumer.handle(AddBlock(block=assistant_block))
        consumer.handle(AddBlock(block=tool_call_block))

        assert len(consumer.blocks) == 3
        assert consumer.blocks[0] is user_block
        assert consumer.blocks[1] is assistant_block
        assert consumer.blocks[2] is tool_call_block

        assert consumer._block_index["block-user-1"] == 0
        assert consumer._block_index["block-assistant-1"] == 1
        assert consumer._block_index["block-tool-1"] == 2


# ---------------------------------------------------------------------------
# Test UpdateBlock event handling
# ---------------------------------------------------------------------------


class TestUpdateBlock:
    """Tests for UpdateBlock event handling."""

    def test_update_block_modifies_existing_content(
        self, consumer: ScreenStateConsumer, tool_call_block: Block
    ) -> None:
        """UpdateBlock modifies existing block content."""
        consumer.handle(AddBlock(block=tool_call_block))

        updated_content = ToolCallContent(
            tool_name="Read",
            tool_use_id="tool-use-1",
            label="README.md",
            result="# Project Title\n\nSome content here.",
        )
        consumer.handle(UpdateBlock(block_id="block-tool-1", content=updated_content))

        assert consumer.blocks[0].content == updated_content

    def test_update_block_preserves_id_type_request_id(
        self, consumer: ScreenStateConsumer, tool_call_block: Block
    ) -> None:
        """UpdateBlock preserves block id, type, request_id."""
        consumer.handle(AddBlock(block=tool_call_block))

        updated_content = ToolCallContent(
            tool_name="Read",
            tool_use_id="tool-use-1",
            label="README.md",
            result="File contents here",
        )
        consumer.handle(UpdateBlock(block_id="block-tool-1", content=updated_content))

        updated_block = consumer.blocks[0]
        assert updated_block.id == "block-tool-1"
        assert updated_block.type == BlockType.TOOL_CALL
        assert updated_block.request_id == "req-123"

    def test_update_block_after_add_block_for_same_block(
        self, consumer: ScreenStateConsumer, tool_call_block: Block
    ) -> None:
        """UpdateBlock after AddBlock for same block."""
        # Add the tool call
        consumer.handle(AddBlock(block=tool_call_block))
        assert consumer.blocks[0].content.result is None

        # Update with result
        updated_content = ToolCallContent(
            tool_name="Read",
            tool_use_id="tool-use-1",
            label="README.md",
            result="Success!",
            is_error=False,
        )
        consumer.handle(UpdateBlock(block_id="block-tool-1", content=updated_content))

        # Verify the update
        assert consumer.blocks[0].content.result == "Success!"
        assert consumer.blocks[0].content.is_error is False


# ---------------------------------------------------------------------------
# Test ClearAll event handling
# ---------------------------------------------------------------------------


class TestClearAll:
    """Tests for ClearAll event handling."""

    def test_clear_all_empties_blocks_and_index(
        self,
        consumer: ScreenStateConsumer,
        user_block: Block,
        assistant_block: Block,
    ) -> None:
        """ClearAll empties blocks and index."""
        consumer.handle(AddBlock(block=user_block))
        consumer.handle(AddBlock(block=assistant_block))

        assert len(consumer.blocks) == 2
        assert len(consumer._block_index) == 2

        consumer.handle(ClearAll())

        assert len(consumer.blocks) == 0
        assert len(consumer._block_index) == 0

    def test_clear_all_followed_by_new_add_block(
        self, consumer: ScreenStateConsumer, user_block: Block, assistant_block: Block
    ) -> None:
        """ClearAll followed by new AddBlock."""
        consumer.handle(AddBlock(block=user_block))
        consumer.handle(ClearAll())
        consumer.handle(AddBlock(block=assistant_block))

        assert len(consumer.blocks) == 1
        assert consumer.blocks[0] is assistant_block
        assert consumer._block_index["block-assistant-1"] == 0
        assert "block-user-1" not in consumer._block_index


# ---------------------------------------------------------------------------
# Test to_markdown() formatting
# ---------------------------------------------------------------------------


class TestToMarkdownUserContent:
    """Tests for to_markdown() with UserContent."""

    def test_formats_user_content_correctly(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """to_markdown() formats UserContent correctly."""
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello, Claude"),
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "❯ Hello, Claude"

    def test_formats_multiline_user_content(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """to_markdown() formats multiline UserContent."""
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Line 1\nLine 2\nLine 3"),
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "❯ Line 1\n  Line 2\n  Line 3"


class TestToMarkdownAssistantContent:
    """Tests for to_markdown() with AssistantContent."""

    def test_formats_assistant_content_correctly(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """to_markdown() formats AssistantContent correctly."""
        block = Block(
            id="block-1",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="Here is my response."),
            request_id="req-1",
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "● Here is my response."

    def test_formats_multiline_assistant_content(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """to_markdown() formats multiline AssistantContent."""
        block = Block(
            id="block-1",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="First line\nSecond line"),
            request_id="req-1",
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "● First line\n  Second line"


class TestToMarkdownToolCallContent:
    """Tests for to_markdown() with ToolCallContent."""

    def test_formats_tool_call_no_result(self, consumer: ScreenStateConsumer) -> None:
        """to_markdown() formats ToolCallContent (no result)."""
        block = Block(
            id="block-1",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Read",
                tool_use_id="tool-1",
                label="config.py",
            ),
            request_id="req-1",
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "● Read(config.py)"

    def test_formats_tool_call_with_result(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """to_markdown() formats ToolCallContent (with result)."""
        block = Block(
            id="block-1",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Bash",
                tool_use_id="tool-1",
                label="List files",
                result="file1.py\nfile2.py",
            ),
            request_id="req-1",
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "● Bash(List files)\n  └ file1.py\n    file2.py"

    def test_formats_tool_call_with_error(self, consumer: ScreenStateConsumer) -> None:
        """to_markdown() formats ToolCallContent (with error)."""
        block = Block(
            id="block-1",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Read",
                tool_use_id="tool-1",
                label="missing.txt",
                result="File not found",
                is_error=True,
            ),
            request_id="req-1",
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "● Read(missing.txt)\n  ✗ File not found"

    def test_formats_tool_call_with_progress(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """to_markdown() formats ToolCallContent (with progress)."""
        block = Block(
            id="block-1",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Bash",
                tool_use_id="tool-1",
                label="Run tests",
                progress_text="Test 5 of 10...",
            ),
            request_id="req-1",
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "● Bash(Run tests)\n  └ Test 5 of 10..."


class TestToMarkdownOtherContent:
    """Tests for to_markdown() with other content types."""

    def test_formats_thinking_content(self, consumer: ScreenStateConsumer) -> None:
        """to_markdown() formats ThinkingContent."""
        block = Block(
            id="block-1",
            type=BlockType.THINKING,
            content=ThinkingContent(),
            request_id="req-1",
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "✱ Thinking…"

    def test_formats_duration_content(self, consumer: ScreenStateConsumer) -> None:
        """to_markdown() formats DurationContent."""
        block = Block(
            id="block-1",
            type=BlockType.DURATION,
            content=DurationContent(duration_ms=65000),  # 1m 5s
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "✱ Crunched for 1m 5s"

    def test_formats_duration_content_seconds_only(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """to_markdown() formats DurationContent with seconds only."""
        block = Block(
            id="block-1",
            type=BlockType.DURATION,
            content=DurationContent(duration_ms=45000),  # 45s
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "✱ Crunched for 45s"

    def test_formats_system_content(self, consumer: ScreenStateConsumer) -> None:
        """to_markdown() formats SystemContent."""
        block = Block(
            id="block-1",
            type=BlockType.SYSTEM,
            content=SystemContent(text="Build completed successfully."),
        )
        consumer.handle(AddBlock(block=block))

        result = consumer.to_markdown()
        assert result == "Build completed successfully."


# ---------------------------------------------------------------------------
# Test request_id grouping
# ---------------------------------------------------------------------------


class TestRequestIdGrouping:
    """Tests for request_id grouping in to_markdown()."""

    def test_groups_by_request_id_no_blank_line(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """to_markdown() groups by request_id (no blank line)."""
        # Two blocks with the same request_id should have no blank line between them
        block1 = Block(
            id="block-1",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="First part"),
            request_id="req-123",
        )
        block2 = Block(
            id="block-2",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Read",
                tool_use_id="tool-1",
                label="file.txt",
            ),
            request_id="req-123",
        )
        consumer.handle(AddBlock(block=block1))
        consumer.handle(AddBlock(block=block2))

        result = consumer.to_markdown()
        # No blank line between blocks with same request_id
        assert result == "● First part\n● Read(file.txt)"

    def test_separates_different_request_ids_blank_line(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """to_markdown() separates different request_ids (blank line)."""
        block1 = Block(
            id="block-1",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="Response 1"),
            request_id="req-1",
        )
        block2 = Block(
            id="block-2",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="Response 2"),
            request_id="req-2",
        )
        consumer.handle(AddBlock(block=block1))
        consumer.handle(AddBlock(block=block2))

        result = consumer.to_markdown()
        # Blank line between blocks with different request_ids
        assert result == "● Response 1\n\n● Response 2"

    def test_separates_none_request_ids_blank_line(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """to_markdown() separates None request_ids (blank line)."""
        # User message (no request_id) followed by duration (no request_id)
        block1 = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        block2 = Block(
            id="block-2",
            type=BlockType.DURATION,
            content=DurationContent(duration_ms=5000),
        )
        consumer.handle(AddBlock(block=block1))
        consumer.handle(AddBlock(block=block2))

        result = consumer.to_markdown()
        # Blank line between blocks with None request_ids
        assert result == "❯ Hello\n\n✱ Crunched for 5s"


# ---------------------------------------------------------------------------
# Test replay_session() convenience function
# ---------------------------------------------------------------------------


class TestReplaySession:
    """Tests for replay_session() convenience function."""

    def test_replay_session_works_end_to_end(self) -> None:
        """replay_session() convenience function works end-to-end."""
        # Create a minimal session with user input and assistant response
        lines = [
            {
                "type": "user",
                "message": {"content": "Hello, Claude", "role": "user"},
            },
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hello! How can I help?"}],
                    "role": "assistant",
                },
                "requestId": "req-123",
            },
        ]

        result = replay_session(lines)

        assert "❯ Hello, Claude" in result
        assert "● Hello! How can I help?" in result

    def test_replay_session_handles_empty_lines(self) -> None:
        """replay_session() handles empty session."""
        result = replay_session([])
        assert result == ""

    def test_replay_session_handles_tool_calls_and_results(self) -> None:
        """replay_session() handles tool calls and results."""
        lines = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-use-abc",
                            "name": "Read",
                            "input": {"file_path": "/path/to/file.txt"},
                        }
                    ],
                    "role": "assistant",
                },
                "requestId": "req-456",
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-use-abc",
                            "content": "File contents here",
                        }
                    ],
                    "role": "user",
                },
            },
        ]

        result = replay_session(lines)

        assert "● Read(file.txt)" in result
        assert "└ File contents here" in result


# ---------------------------------------------------------------------------
# Test format helper functions
# ---------------------------------------------------------------------------


class TestFormatHelpers:
    """Tests for format helper functions."""

    def test_format_user_text_empty(self) -> None:
        """format_user_text handles empty string."""
        assert format_user_text("") == "❯"

    def test_format_assistant_text_empty(self) -> None:
        """format_assistant_text handles empty string."""
        assert format_assistant_text("") == "●"

    def test_format_tool_call_result_priority_over_progress(self) -> None:
        """format_tool_call gives result priority over progress."""
        content = ToolCallContent(
            tool_name="Bash",
            tool_use_id="tool-1",
            label="cmd",
            result="final output",
            progress_text="still running...",
        )

        result = format_tool_call(content)
        assert "final output" in result
        assert "still running" not in result

    def test_format_block_with_all_content_types(self) -> None:
        """format_block handles all content types."""
        # Test each content type
        user_block = Block(
            id="1", type=BlockType.USER, content=UserContent(text="test")
        )
        assert format_block(user_block) == "❯ test"

        assistant_block = Block(
            id="2", type=BlockType.ASSISTANT, content=AssistantContent(text="response")
        )
        assert format_block(assistant_block) == "● response"

        thinking_block = Block(
            id="3", type=BlockType.THINKING, content=ThinkingContent()
        )
        assert format_block(thinking_block) == "✱ Thinking…"

        duration_block = Block(
            id="4", type=BlockType.DURATION, content=DurationContent(duration_ms=30000)
        )
        assert format_block(duration_block) == "✱ Crunched for 30s"

        system_block = Block(
            id="5", type=BlockType.SYSTEM, content=SystemContent(text="output")
        )
        assert format_block(system_block) == "output"


# ---------------------------------------------------------------------------
# Test async Consumer protocol implementation
# ---------------------------------------------------------------------------


class TestAsyncOnEvent:
    """Tests for the async on_event() method."""

    @pytest.mark.asyncio
    async def test_on_event_handles_add_block(
        self, consumer: ScreenStateConsumer, user_block: Block
    ) -> None:
        """on_event() handles AddBlock events."""
        await consumer.on_event(AddBlock(block=user_block))
        assert len(consumer.blocks) == 1
        assert consumer.blocks[0] is user_block

    @pytest.mark.asyncio
    async def test_on_event_handles_update_block(
        self, consumer: ScreenStateConsumer, tool_call_block: Block
    ) -> None:
        """on_event() handles UpdateBlock events."""
        await consumer.on_event(AddBlock(block=tool_call_block))

        updated_content = ToolCallContent(
            tool_name="Read",
            tool_use_id="tool-use-1",
            label="README.md",
            result="File contents here",
        )
        await consumer.on_event(
            UpdateBlock(block_id="block-tool-1", content=updated_content)
        )

        assert consumer.blocks[0].content.result == "File contents here"

    @pytest.mark.asyncio
    async def test_on_event_handles_clear_all(
        self, consumer: ScreenStateConsumer, user_block: Block, assistant_block: Block
    ) -> None:
        """on_event() handles ClearAll events."""
        await consumer.on_event(AddBlock(block=user_block))
        await consumer.on_event(AddBlock(block=assistant_block))

        assert len(consumer.blocks) == 2

        await consumer.on_event(ClearAll())

        assert len(consumer.blocks) == 0
        assert len(consumer._block_index) == 0

    @pytest.mark.asyncio
    async def test_on_event_produces_same_result_as_handle(
        self, user_block: Block, assistant_block: Block, tool_call_block: Block
    ) -> None:
        """on_event() and handle() produce identical results."""
        # Create two consumers
        sync_consumer = ScreenStateConsumer()
        async_consumer = ScreenStateConsumer()

        # Process same events via sync handle()
        sync_consumer.handle(AddBlock(block=user_block))
        sync_consumer.handle(AddBlock(block=assistant_block))
        sync_consumer.handle(AddBlock(block=tool_call_block))

        # Process same events via async on_event()
        await async_consumer.on_event(AddBlock(block=user_block))
        await async_consumer.on_event(AddBlock(block=assistant_block))
        await async_consumer.on_event(AddBlock(block=tool_call_block))

        # Results should be identical
        assert sync_consumer.to_markdown() == async_consumer.to_markdown()


class TestRenderBlock:
    """Tests for the render_block() method."""

    def test_render_block_returns_same_as_format_block(
        self, consumer: ScreenStateConsumer, user_block: Block
    ) -> None:
        """render_block() returns same result as format_block()."""
        result = consumer.render_block(user_block)
        expected = format_block(user_block)
        assert result == expected

    def test_render_block_for_user_content(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """render_block() formats UserContent correctly."""
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        assert consumer.render_block(block) == "❯ Hello"

    def test_render_block_for_assistant_content(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """render_block() formats AssistantContent correctly."""
        block = Block(
            id="block-1",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="Hi there!"),
            request_id="req-1",
        )
        assert consumer.render_block(block) == "● Hi there!"

    def test_render_block_for_tool_call_with_result(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """render_block() formats ToolCallContent with result."""
        block = Block(
            id="block-1",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Bash",
                tool_use_id="tool-1",
                label="List files",
                result="file.txt",
            ),
            request_id="req-1",
        )
        assert consumer.render_block(block) == "● Bash(List files)\n  └ file.txt"

    def test_render_block_for_thinking_content(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """render_block() formats ThinkingContent correctly."""
        block = Block(
            id="block-1",
            type=BlockType.THINKING,
            content=ThinkingContent(),
            request_id="req-1",
        )
        assert consumer.render_block(block) == "✱ Thinking…"

    def test_render_block_for_duration_content(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """render_block() formats DurationContent correctly."""
        block = Block(
            id="block-1",
            type=BlockType.DURATION,
            content=DurationContent(duration_ms=30000),
        )
        assert consumer.render_block(block) == "✱ Crunched for 30s"

    def test_render_block_for_system_content(
        self, consumer: ScreenStateConsumer
    ) -> None:
        """render_block() formats SystemContent correctly."""
        block = Block(
            id="block-1",
            type=BlockType.SYSTEM,
            content=SystemContent(text="System message"),
        )
        assert consumer.render_block(block) == "System message"


class TestConsumerProtocolCompliance:
    """Tests for Consumer protocol compliance."""

    def test_consumer_implements_protocol(self) -> None:
        """ScreenStateConsumer implements Consumer protocol."""
        from claude_session_player.protocol import Consumer

        consumer = ScreenStateConsumer()
        assert isinstance(consumer, Consumer)

    def test_consumer_can_be_used_with_emitter(self) -> None:
        """ScreenStateConsumer can be subscribed to EventEmitter."""
        from claude_session_player.emitter import EventEmitter

        emitter = EventEmitter()
        consumer = ScreenStateConsumer()

        # Should not raise
        emitter.subscribe(consumer)
        assert emitter.subscriber_count == 1

    @pytest.mark.asyncio
    async def test_consumer_works_with_emitter_emit(
        self, user_block: Block
    ) -> None:
        """ScreenStateConsumer processes events from EventEmitter."""
        import asyncio
        from claude_session_player.emitter import EventEmitter

        emitter = EventEmitter()
        consumer = ScreenStateConsumer()
        emitter.subscribe(consumer)

        # Emit an event
        await emitter.emit(AddBlock(block=user_block))

        # Wait for fire-and-forget task to complete
        await asyncio.sleep(0.01)

        # Consumer should have processed the event
        assert len(consumer.blocks) == 1
        assert consumer.blocks[0] is user_block
