"""Tests for the event-driven renderer data model."""

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockContent,
    BlockType,
    ClearAll,
    DurationContent,
    Event,
    ProcessingContext,
    SystemContent,
    ThinkingContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)


class TestBlockType:
    """Tests for BlockType enum."""

    def test_block_type_has_seven_values(self) -> None:
        """BlockType enum has exactly 7 values."""
        assert len(BlockType) == 7

    def test_block_type_user(self) -> None:
        """USER block type has correct value."""
        assert BlockType.USER.value == "user"

    def test_block_type_assistant(self) -> None:
        """ASSISTANT block type has correct value."""
        assert BlockType.ASSISTANT.value == "assistant"

    def test_block_type_tool_call(self) -> None:
        """TOOL_CALL block type has correct value."""
        assert BlockType.TOOL_CALL.value == "tool_call"

    def test_block_type_question(self) -> None:
        """QUESTION block type has correct value."""
        assert BlockType.QUESTION.value == "question"

    def test_block_type_thinking(self) -> None:
        """THINKING block type has correct value."""
        assert BlockType.THINKING.value == "thinking"

    def test_block_type_duration(self) -> None:
        """DURATION block type has correct value."""
        assert BlockType.DURATION.value == "duration"

    def test_block_type_system(self) -> None:
        """SYSTEM block type has correct value."""
        assert BlockType.SYSTEM.value == "system"


class TestBlockContent:
    """Tests for BlockContent dataclasses."""

    def test_user_content_instantiation(self) -> None:
        """UserContent can be instantiated with text."""
        content = UserContent(text="Hello, Claude!")
        assert content.text == "Hello, Claude!"

    def test_assistant_content_instantiation(self) -> None:
        """AssistantContent can be instantiated with text."""
        content = AssistantContent(text="Hello! How can I help?")
        assert content.text == "Hello! How can I help?"

    def test_tool_call_content_required_fields(self) -> None:
        """ToolCallContent can be instantiated with required fields only."""
        content = ToolCallContent(
            tool_name="Bash",
            tool_use_id="toolu_123",
            label="List files",
        )
        assert content.tool_name == "Bash"
        assert content.tool_use_id == "toolu_123"
        assert content.label == "List files"
        assert content.result is None
        assert content.is_error is False
        assert content.progress_text is None

    def test_tool_call_content_all_fields(self) -> None:
        """ToolCallContent can be instantiated with all fields."""
        content = ToolCallContent(
            tool_name="Bash",
            tool_use_id="toolu_123",
            label="List files",
            result="file1.txt\nfile2.txt",
            is_error=False,
            progress_text="Running command...",
        )
        assert content.result == "file1.txt\nfile2.txt"
        assert content.is_error is False
        assert content.progress_text == "Running command..."

    def test_tool_call_content_error_state(self) -> None:
        """ToolCallContent can represent error results."""
        content = ToolCallContent(
            tool_name="Bash",
            tool_use_id="toolu_456",
            label="Run command",
            result="Permission denied",
            is_error=True,
        )
        assert content.is_error is True
        assert content.result == "Permission denied"

    def test_thinking_content_instantiation(self) -> None:
        """ThinkingContent can be instantiated (no fields)."""
        content = ThinkingContent()
        assert isinstance(content, ThinkingContent)

    def test_duration_content_instantiation(self) -> None:
        """DurationContent can be instantiated with duration_ms."""
        content = DurationContent(duration_ms=5000)
        assert content.duration_ms == 5000

    def test_system_content_instantiation(self) -> None:
        """SystemContent can be instantiated with text."""
        content = SystemContent(text="System message")
        assert content.text == "System message"


class TestBlock:
    """Tests for Block dataclass."""

    def test_block_creation_with_all_fields(self) -> None:
        """Block can be created with all fields including request_id."""
        content = UserContent(text="Hello")
        block = Block(
            id="block-123",
            type=BlockType.USER,
            content=content,
            request_id="req-456",
        )
        assert block.id == "block-123"
        assert block.type == BlockType.USER
        assert block.content == content
        assert block.request_id == "req-456"

    def test_block_creation_with_defaults(self) -> None:
        """Block can be created with default request_id=None."""
        content = AssistantContent(text="Response")
        block = Block(
            id="block-789",
            type=BlockType.ASSISTANT,
            content=content,
        )
        assert block.id == "block-789"
        assert block.type == BlockType.ASSISTANT
        assert block.content == content
        assert block.request_id is None

    def test_block_equality_same_id(self) -> None:
        """Blocks with same fields are equal (dataclass default)."""
        content1 = UserContent(text="Hello")
        content2 = UserContent(text="Hello")
        block1 = Block(id="same-id", type=BlockType.USER, content=content1)
        block2 = Block(id="same-id", type=BlockType.USER, content=content2)
        assert block1 == block2

    def test_block_inequality_different_id(self) -> None:
        """Blocks with different IDs are not equal."""
        content = UserContent(text="Hello")
        block1 = Block(id="id-1", type=BlockType.USER, content=content)
        block2 = Block(id="id-2", type=BlockType.USER, content=content)
        assert block1 != block2

    def test_block_with_tool_call_content(self) -> None:
        """Block can hold ToolCallContent."""
        content = ToolCallContent(
            tool_name="Read",
            tool_use_id="toolu_abc",
            label="config.py",
        )
        block = Block(
            id="tool-block",
            type=BlockType.TOOL_CALL,
            content=content,
            request_id="req-xyz",
        )
        assert block.type == BlockType.TOOL_CALL
        assert isinstance(block.content, ToolCallContent)
        assert block.content.tool_name == "Read"

    def test_block_with_thinking_content(self) -> None:
        """Block can hold ThinkingContent."""
        content = ThinkingContent()
        block = Block(
            id="thinking-block",
            type=BlockType.THINKING,
            content=content,
        )
        assert block.type == BlockType.THINKING
        assert isinstance(block.content, ThinkingContent)

    def test_block_with_duration_content(self) -> None:
        """Block can hold DurationContent."""
        content = DurationContent(duration_ms=12345)
        block = Block(
            id="duration-block",
            type=BlockType.DURATION,
            content=content,
        )
        assert block.type == BlockType.DURATION
        assert isinstance(block.content, DurationContent)
        assert block.content.duration_ms == 12345

    def test_block_with_system_content(self) -> None:
        """Block can hold SystemContent."""
        content = SystemContent(text="Orphan tool result")
        block = Block(
            id="system-block",
            type=BlockType.SYSTEM,
            content=content,
        )
        assert block.type == BlockType.SYSTEM
        assert isinstance(block.content, SystemContent)


class TestEvents:
    """Tests for Event types."""

    def test_add_block_event(self) -> None:
        """AddBlock event holds a Block."""
        content = UserContent(text="Test input")
        block = Block(id="blk-1", type=BlockType.USER, content=content)
        event = AddBlock(block=block)

        assert isinstance(event, AddBlock)
        assert event.block == block
        assert event.block.id == "blk-1"

    def test_update_block_event(self) -> None:
        """UpdateBlock event holds block_id and new content."""
        new_content = ToolCallContent(
            tool_name="Bash",
            tool_use_id="toolu_123",
            label="Run test",
            result="All tests passed",
            is_error=False,
        )
        event = UpdateBlock(block_id="blk-2", content=new_content)

        assert isinstance(event, UpdateBlock)
        assert event.block_id == "blk-2"
        assert event.content == new_content
        assert isinstance(event.content, ToolCallContent)

    def test_clear_all_event(self) -> None:
        """ClearAll event has no fields."""
        event = ClearAll()

        assert isinstance(event, ClearAll)

    def test_event_union_accepts_add_block(self) -> None:
        """Event union type accepts AddBlock."""
        content = AssistantContent(text="Hi")
        block = Block(id="b1", type=BlockType.ASSISTANT, content=content)
        event: Event = AddBlock(block=block)
        assert isinstance(event, AddBlock)

    def test_event_union_accepts_update_block(self) -> None:
        """Event union type accepts UpdateBlock."""
        content = SystemContent(text="Updated")
        event: Event = UpdateBlock(block_id="b2", content=content)
        assert isinstance(event, UpdateBlock)

    def test_event_union_accepts_clear_all(self) -> None:
        """Event union type accepts ClearAll."""
        event: Event = ClearAll()
        assert isinstance(event, ClearAll)


class TestProcessingContext:
    """Tests for ProcessingContext."""

    def test_context_initialization_empty(self) -> None:
        """ProcessingContext initializes with empty dict and None request_id."""
        ctx = ProcessingContext()
        assert ctx.tool_use_id_to_block_id == {}
        assert ctx.current_request_id is None

    def test_context_stores_tool_mapping(self) -> None:
        """ProcessingContext can store tool_use_id to block_id mappings."""
        ctx = ProcessingContext()
        ctx.tool_use_id_to_block_id["toolu_123"] = "block-456"
        ctx.tool_use_id_to_block_id["toolu_789"] = "block-abc"

        assert ctx.tool_use_id_to_block_id["toolu_123"] == "block-456"
        assert ctx.tool_use_id_to_block_id["toolu_789"] == "block-abc"
        assert len(ctx.tool_use_id_to_block_id) == 2

    def test_context_stores_current_request_id(self) -> None:
        """ProcessingContext can store current_request_id."""
        ctx = ProcessingContext()
        ctx.current_request_id = "req-xyz"
        assert ctx.current_request_id == "req-xyz"

    def test_context_clear_resets_all_fields(self) -> None:
        """ProcessingContext.clear() resets all fields."""
        ctx = ProcessingContext()
        ctx.tool_use_id_to_block_id["toolu_1"] = "block-1"
        ctx.tool_use_id_to_block_id["toolu_2"] = "block-2"
        ctx.current_request_id = "req-123"

        ctx.clear()

        assert ctx.tool_use_id_to_block_id == {}
        assert ctx.current_request_id is None

    def test_context_clear_is_idempotent(self) -> None:
        """ProcessingContext.clear() can be called multiple times safely."""
        ctx = ProcessingContext()
        ctx.clear()
        ctx.clear()
        assert ctx.tool_use_id_to_block_id == {}
        assert ctx.current_request_id is None

    def test_context_with_initial_values(self) -> None:
        """ProcessingContext can be created with initial values."""
        initial_mapping = {"tool-1": "block-1"}
        ctx = ProcessingContext(
            tool_use_id_to_block_id=initial_mapping,
            current_request_id="initial-req",
        )
        assert ctx.tool_use_id_to_block_id == {"tool-1": "block-1"}
        assert ctx.current_request_id == "initial-req"
