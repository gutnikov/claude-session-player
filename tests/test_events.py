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
    Question,
    QuestionContent,
    QuestionOption,
    SystemContent,
    ThinkingContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
    content_from_dict,
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


# ===========================================================================
# Serialization Tests (Issue #48)
# ===========================================================================


class TestUserContentSerialization:
    """Tests for UserContent to_dict/from_dict."""

    def test_to_dict_returns_expected_dict(self) -> None:
        """UserContent.to_dict() returns dict with type discriminator."""
        content = UserContent(text="Hello, Claude!")
        result = content.to_dict()
        assert result == {"type": "user", "text": "Hello, Claude!"}

    def test_from_dict_reconstructs_object(self) -> None:
        """UserContent.from_dict() reconstructs the object."""
        data = {"type": "user", "text": "Hello, Claude!"}
        content = UserContent.from_dict(data)
        assert content.text == "Hello, Claude!"

    def test_round_trip(self) -> None:
        """Round-trip: obj == Cls.from_dict(obj.to_dict())."""
        original = UserContent(text="Test message")
        restored = UserContent.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_empty_text(self) -> None:
        """Round-trip works with empty text."""
        original = UserContent(text="")
        restored = UserContent.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_multiline_text(self) -> None:
        """Round-trip works with multiline text."""
        original = UserContent(text="line1\nline2\nline3")
        restored = UserContent.from_dict(original.to_dict())
        assert restored == original


class TestAssistantContentSerialization:
    """Tests for AssistantContent to_dict/from_dict."""

    def test_to_dict_returns_expected_dict(self) -> None:
        """AssistantContent.to_dict() returns dict with type discriminator."""
        content = AssistantContent(text="Hello! How can I help?")
        result = content.to_dict()
        assert result == {"type": "assistant", "text": "Hello! How can I help?"}

    def test_from_dict_reconstructs_object(self) -> None:
        """AssistantContent.from_dict() reconstructs the object."""
        data = {"type": "assistant", "text": "Response text"}
        content = AssistantContent.from_dict(data)
        assert content.text == "Response text"

    def test_round_trip(self) -> None:
        """Round-trip: obj == Cls.from_dict(obj.to_dict())."""
        original = AssistantContent(text="Here is my response.")
        restored = AssistantContent.from_dict(original.to_dict())
        assert restored == original


class TestToolCallContentSerialization:
    """Tests for ToolCallContent to_dict/from_dict."""

    def test_to_dict_returns_expected_dict_required_fields(self) -> None:
        """ToolCallContent.to_dict() with required fields only."""
        content = ToolCallContent(
            tool_name="Bash",
            tool_use_id="toolu_123",
            label="List files",
        )
        result = content.to_dict()
        assert result == {
            "type": "tool_call",
            "tool_name": "Bash",
            "tool_use_id": "toolu_123",
            "label": "List files",
            "result": None,
            "is_error": False,
            "progress_text": None,
        }

    def test_to_dict_returns_expected_dict_all_fields(self) -> None:
        """ToolCallContent.to_dict() with all fields populated."""
        content = ToolCallContent(
            tool_name="Bash",
            tool_use_id="toolu_456",
            label="Run tests",
            result="All tests passed",
            is_error=False,
            progress_text="Running...",
        )
        result = content.to_dict()
        assert result == {
            "type": "tool_call",
            "tool_name": "Bash",
            "tool_use_id": "toolu_456",
            "label": "Run tests",
            "result": "All tests passed",
            "is_error": False,
            "progress_text": "Running...",
        }

    def test_to_dict_error_state(self) -> None:
        """ToolCallContent.to_dict() with is_error=True."""
        content = ToolCallContent(
            tool_name="Bash",
            tool_use_id="toolu_789",
            label="Run command",
            result="Permission denied",
            is_error=True,
        )
        result = content.to_dict()
        assert result["is_error"] is True
        assert result["result"] == "Permission denied"

    def test_from_dict_reconstructs_object(self) -> None:
        """ToolCallContent.from_dict() reconstructs the object."""
        data = {
            "type": "tool_call",
            "tool_name": "Read",
            "tool_use_id": "toolu_abc",
            "label": "config.py",
            "result": "file contents",
            "is_error": False,
            "progress_text": "Reading...",
        }
        content = ToolCallContent.from_dict(data)
        assert content.tool_name == "Read"
        assert content.tool_use_id == "toolu_abc"
        assert content.label == "config.py"
        assert content.result == "file contents"
        assert content.is_error is False
        assert content.progress_text == "Reading..."

    def test_from_dict_with_missing_optional_fields(self) -> None:
        """ToolCallContent.from_dict() uses defaults for missing optional fields."""
        data = {
            "type": "tool_call",
            "tool_name": "Bash",
            "tool_use_id": "toolu_minimal",
            "label": "Command",
        }
        content = ToolCallContent.from_dict(data)
        assert content.tool_name == "Bash"
        assert content.tool_use_id == "toolu_minimal"
        assert content.label == "Command"
        assert content.result is None
        assert content.is_error is False
        assert content.progress_text is None

    def test_round_trip(self) -> None:
        """Round-trip: obj == Cls.from_dict(obj.to_dict())."""
        original = ToolCallContent(
            tool_name="Write",
            tool_use_id="toolu_write",
            label="output.txt",
            result="File written",
            is_error=False,
            progress_text="Writing...",
        )
        restored = ToolCallContent.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_minimal(self) -> None:
        """Round-trip with only required fields."""
        original = ToolCallContent(
            tool_name="Glob",
            tool_use_id="toolu_glob",
            label="**/*.py",
        )
        restored = ToolCallContent.from_dict(original.to_dict())
        assert restored == original


class TestThinkingContentSerialization:
    """Tests for ThinkingContent to_dict/from_dict."""

    def test_to_dict_returns_expected_dict(self) -> None:
        """ThinkingContent.to_dict() returns dict with only type discriminator."""
        content = ThinkingContent()
        result = content.to_dict()
        assert result == {"type": "thinking"}

    def test_from_dict_reconstructs_object(self) -> None:
        """ThinkingContent.from_dict() reconstructs the object."""
        data = {"type": "thinking"}
        content = ThinkingContent.from_dict(data)
        assert isinstance(content, ThinkingContent)

    def test_round_trip(self) -> None:
        """Round-trip: obj == Cls.from_dict(obj.to_dict())."""
        original = ThinkingContent()
        restored = ThinkingContent.from_dict(original.to_dict())
        assert restored == original


class TestDurationContentSerialization:
    """Tests for DurationContent to_dict/from_dict."""

    def test_to_dict_returns_expected_dict(self) -> None:
        """DurationContent.to_dict() returns dict with type and duration_ms."""
        content = DurationContent(duration_ms=5000)
        result = content.to_dict()
        assert result == {"type": "duration", "duration_ms": 5000}

    def test_from_dict_reconstructs_object(self) -> None:
        """DurationContent.from_dict() reconstructs the object."""
        data = {"type": "duration", "duration_ms": 12345}
        content = DurationContent.from_dict(data)
        assert content.duration_ms == 12345

    def test_round_trip(self) -> None:
        """Round-trip: obj == Cls.from_dict(obj.to_dict())."""
        original = DurationContent(duration_ms=98765)
        restored = DurationContent.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_zero_duration(self) -> None:
        """Round-trip with zero duration."""
        original = DurationContent(duration_ms=0)
        restored = DurationContent.from_dict(original.to_dict())
        assert restored == original


class TestSystemContentSerialization:
    """Tests for SystemContent to_dict/from_dict."""

    def test_to_dict_returns_expected_dict(self) -> None:
        """SystemContent.to_dict() returns dict with type and text."""
        content = SystemContent(text="System message")
        result = content.to_dict()
        assert result == {"type": "system", "text": "System message"}

    def test_from_dict_reconstructs_object(self) -> None:
        """SystemContent.from_dict() reconstructs the object."""
        data = {"type": "system", "text": "Orphan tool result"}
        content = SystemContent.from_dict(data)
        assert content.text == "Orphan tool result"

    def test_round_trip(self) -> None:
        """Round-trip: obj == Cls.from_dict(obj.to_dict())."""
        original = SystemContent(text="System output here")
        restored = SystemContent.from_dict(original.to_dict())
        assert restored == original


class TestQuestionOptionSerialization:
    """Tests for QuestionOption to_dict/from_dict."""

    def test_to_dict_returns_expected_dict(self) -> None:
        """QuestionOption.to_dict() returns dict with label and description."""
        opt = QuestionOption(label="Option A", description="Description for A")
        result = opt.to_dict()
        assert result == {"label": "Option A", "description": "Description for A"}

    def test_from_dict_reconstructs_object(self) -> None:
        """QuestionOption.from_dict() reconstructs the object."""
        data = {"label": "Option B", "description": "Description for B"}
        opt = QuestionOption.from_dict(data)
        assert opt.label == "Option B"
        assert opt.description == "Description for B"

    def test_round_trip(self) -> None:
        """Round-trip: obj == Cls.from_dict(obj.to_dict())."""
        original = QuestionOption(label="uv (Recommended)", description="Fast Python package manager")
        restored = QuestionOption.from_dict(original.to_dict())
        assert restored == original


class TestQuestionSerialization:
    """Tests for Question to_dict/from_dict."""

    def test_to_dict_returns_expected_dict(self) -> None:
        """Question.to_dict() returns dict with all fields."""
        q = Question(
            question="Which package manager?",
            header="Pkg manager",
            options=[
                QuestionOption(label="uv", description="Fast"),
                QuestionOption(label="pip", description="Standard"),
            ],
            multi_select=False,
        )
        result = q.to_dict()
        assert result == {
            "question": "Which package manager?",
            "header": "Pkg manager",
            "options": [
                {"label": "uv", "description": "Fast"},
                {"label": "pip", "description": "Standard"},
            ],
            "multi_select": False,
        }

    def test_from_dict_reconstructs_object(self) -> None:
        """Question.from_dict() reconstructs the object."""
        data = {
            "question": "Select features",
            "header": "Features",
            "options": [
                {"label": "Auth", "description": "Authentication"},
                {"label": "API", "description": "REST API"},
            ],
            "multi_select": True,
        }
        q = Question.from_dict(data)
        assert q.question == "Select features"
        assert q.header == "Features"
        assert len(q.options) == 2
        assert q.options[0].label == "Auth"
        assert q.multi_select is True

    def test_from_dict_with_missing_multi_select(self) -> None:
        """Question.from_dict() defaults multi_select to False."""
        data = {
            "question": "Which option?",
            "header": "Choice",
            "options": [{"label": "A", "description": "Option A"}],
        }
        q = Question.from_dict(data)
        assert q.multi_select is False

    def test_round_trip(self) -> None:
        """Round-trip: obj == Cls.from_dict(obj.to_dict())."""
        original = Question(
            question="How should we proceed?",
            header="Approach",
            options=[
                QuestionOption(label="Fast", description="Quick implementation"),
                QuestionOption(label="Thorough", description="Comprehensive approach"),
            ],
            multi_select=False,
        )
        restored = Question.from_dict(original.to_dict())
        assert restored == original


class TestQuestionContentSerialization:
    """Tests for QuestionContent to_dict/from_dict."""

    def test_to_dict_returns_expected_dict_no_answers(self) -> None:
        """QuestionContent.to_dict() without answers."""
        content = QuestionContent(
            tool_use_id="toolu_q1",
            questions=[
                Question(
                    question="Which DB?",
                    header="Database",
                    options=[
                        QuestionOption(label="PostgreSQL", description="Relational"),
                        QuestionOption(label="MongoDB", description="Document"),
                    ],
                )
            ],
            answers=None,
        )
        result = content.to_dict()
        assert result == {
            "type": "question",
            "tool_use_id": "toolu_q1",
            "questions": [
                {
                    "question": "Which DB?",
                    "header": "Database",
                    "options": [
                        {"label": "PostgreSQL", "description": "Relational"},
                        {"label": "MongoDB", "description": "Document"},
                    ],
                    "multi_select": False,
                }
            ],
            "answers": None,
        }

    def test_to_dict_returns_expected_dict_with_answers(self) -> None:
        """QuestionContent.to_dict() with answers."""
        content = QuestionContent(
            tool_use_id="toolu_q2",
            questions=[
                Question(
                    question="Which framework?",
                    header="Framework",
                    options=[QuestionOption(label="FastAPI", description="Modern")],
                )
            ],
            answers={"0": "FastAPI"},
        )
        result = content.to_dict()
        assert result["answers"] == {"0": "FastAPI"}

    def test_from_dict_reconstructs_object(self) -> None:
        """QuestionContent.from_dict() reconstructs the object."""
        data = {
            "type": "question",
            "tool_use_id": "toolu_q3",
            "questions": [
                {
                    "question": "Select environment",
                    "header": "Env",
                    "options": [{"label": "Dev", "description": "Development"}],
                    "multi_select": False,
                }
            ],
            "answers": {"0": "Dev"},
        }
        content = QuestionContent.from_dict(data)
        assert content.tool_use_id == "toolu_q3"
        assert len(content.questions) == 1
        assert content.questions[0].question == "Select environment"
        assert content.answers == {"0": "Dev"}

    def test_from_dict_with_missing_answers(self) -> None:
        """QuestionContent.from_dict() with missing answers field."""
        data = {
            "type": "question",
            "tool_use_id": "toolu_q4",
            "questions": [],
        }
        content = QuestionContent.from_dict(data)
        assert content.answers is None

    def test_round_trip(self) -> None:
        """Round-trip: obj == Cls.from_dict(obj.to_dict())."""
        original = QuestionContent(
            tool_use_id="toolu_q5",
            questions=[
                Question(
                    question="Multiple choice?",
                    header="Multi",
                    options=[
                        QuestionOption(label="A", description="First"),
                        QuestionOption(label="B", description="Second"),
                    ],
                    multi_select=True,
                )
            ],
            answers={"0": "A,B"},
        )
        restored = QuestionContent.from_dict(original.to_dict())
        assert restored == original


class TestContentFromDict:
    """Tests for content_from_dict dispatcher function."""

    def test_dispatches_user_content(self) -> None:
        """content_from_dict correctly dispatches to UserContent."""
        data = {"type": "user", "text": "Hello"}
        content = content_from_dict(data)
        assert isinstance(content, UserContent)
        assert content.text == "Hello"

    def test_dispatches_assistant_content(self) -> None:
        """content_from_dict correctly dispatches to AssistantContent."""
        data = {"type": "assistant", "text": "Hi there"}
        content = content_from_dict(data)
        assert isinstance(content, AssistantContent)
        assert content.text == "Hi there"

    def test_dispatches_tool_call_content(self) -> None:
        """content_from_dict correctly dispatches to ToolCallContent."""
        data = {
            "type": "tool_call",
            "tool_name": "Bash",
            "tool_use_id": "toolu_1",
            "label": "ls",
        }
        content = content_from_dict(data)
        assert isinstance(content, ToolCallContent)
        assert content.tool_name == "Bash"

    def test_dispatches_question_content(self) -> None:
        """content_from_dict correctly dispatches to QuestionContent."""
        data = {
            "type": "question",
            "tool_use_id": "toolu_q",
            "questions": [],
        }
        content = content_from_dict(data)
        assert isinstance(content, QuestionContent)

    def test_dispatches_thinking_content(self) -> None:
        """content_from_dict correctly dispatches to ThinkingContent."""
        data = {"type": "thinking"}
        content = content_from_dict(data)
        assert isinstance(content, ThinkingContent)

    def test_dispatches_duration_content(self) -> None:
        """content_from_dict correctly dispatches to DurationContent."""
        data = {"type": "duration", "duration_ms": 1000}
        content = content_from_dict(data)
        assert isinstance(content, DurationContent)
        assert content.duration_ms == 1000

    def test_dispatches_system_content(self) -> None:
        """content_from_dict correctly dispatches to SystemContent."""
        data = {"type": "system", "text": "Output"}
        content = content_from_dict(data)
        assert isinstance(content, SystemContent)
        assert content.text == "Output"

    def test_raises_key_error_for_unknown_type(self) -> None:
        """content_from_dict raises KeyError for unknown type."""
        data = {"type": "unknown_type", "foo": "bar"}
        with pytest.raises(KeyError):
            content_from_dict(data)

    def test_raises_key_error_for_missing_type(self) -> None:
        """content_from_dict raises KeyError when type field is missing."""
        data = {"text": "no type field"}
        with pytest.raises(KeyError):
            content_from_dict(data)


class TestBlockSerialization:
    """Tests for Block to_dict/from_dict."""

    def test_to_dict_returns_expected_dict(self) -> None:
        """Block.to_dict() returns dict with all fields."""
        content = UserContent(text="Hello")
        block = Block(
            id="block-123",
            type=BlockType.USER,
            content=content,
            request_id="req-456",
        )
        result = block.to_dict()
        assert result == {
            "id": "block-123",
            "type": "user",
            "content": {"type": "user", "text": "Hello"},
            "request_id": "req-456",
        }

    def test_to_dict_with_none_request_id(self) -> None:
        """Block.to_dict() with request_id=None."""
        content = AssistantContent(text="Response")
        block = Block(id="block-789", type=BlockType.ASSISTANT, content=content)
        result = block.to_dict()
        assert result["request_id"] is None

    def test_from_dict_reconstructs_object(self) -> None:
        """Block.from_dict() reconstructs the object using content_from_dict."""
        data = {
            "id": "block-abc",
            "type": "tool_call",
            "content": {
                "type": "tool_call",
                "tool_name": "Read",
                "tool_use_id": "toolu_read",
                "label": "file.py",
            },
            "request_id": "req-xyz",
        }
        block = Block.from_dict(data)
        assert block.id == "block-abc"
        assert block.type == BlockType.TOOL_CALL
        assert isinstance(block.content, ToolCallContent)
        assert block.content.tool_name == "Read"
        assert block.request_id == "req-xyz"

    def test_from_dict_with_missing_request_id(self) -> None:
        """Block.from_dict() handles missing request_id."""
        data = {
            "id": "block-minimal",
            "type": "system",
            "content": {"type": "system", "text": "output"},
        }
        block = Block.from_dict(data)
        assert block.request_id is None

    def test_round_trip_user_block(self) -> None:
        """Round-trip for USER block."""
        original = Block(
            id="user-block",
            type=BlockType.USER,
            content=UserContent(text="User input"),
        )
        restored = Block.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_assistant_block(self) -> None:
        """Round-trip for ASSISTANT block."""
        original = Block(
            id="assistant-block",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="Assistant response"),
            request_id="req-1",
        )
        restored = Block.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_tool_call_block(self) -> None:
        """Round-trip for TOOL_CALL block."""
        original = Block(
            id="tool-block",
            type=BlockType.TOOL_CALL,
            content=ToolCallContent(
                tool_name="Bash",
                tool_use_id="toolu_bash",
                label="Command",
                result="output",
                is_error=False,
            ),
            request_id="req-2",
        )
        restored = Block.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_question_block(self) -> None:
        """Round-trip for QUESTION block."""
        original = Block(
            id="question-block",
            type=BlockType.QUESTION,
            content=QuestionContent(
                tool_use_id="toolu_q",
                questions=[
                    Question(
                        question="Choose?",
                        header="Choice",
                        options=[QuestionOption(label="A", description="First")],
                    )
                ],
                answers={"0": "A"},
            ),
        )
        restored = Block.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_thinking_block(self) -> None:
        """Round-trip for THINKING block."""
        original = Block(
            id="thinking-block",
            type=BlockType.THINKING,
            content=ThinkingContent(),
        )
        restored = Block.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_duration_block(self) -> None:
        """Round-trip for DURATION block."""
        original = Block(
            id="duration-block",
            type=BlockType.DURATION,
            content=DurationContent(duration_ms=5000),
        )
        restored = Block.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_system_block(self) -> None:
        """Round-trip for SYSTEM block."""
        original = Block(
            id="system-block",
            type=BlockType.SYSTEM,
            content=SystemContent(text="System output"),
        )
        restored = Block.from_dict(original.to_dict())
        assert restored == original


class TestProcessingContextSerialization:
    """Tests for ProcessingContext to_dict/from_dict."""

    def test_to_dict_returns_expected_dict_empty(self) -> None:
        """ProcessingContext.to_dict() with default values."""
        ctx = ProcessingContext()
        result = ctx.to_dict()
        assert result == {
            "tool_use_id_to_block_id": {},
            "current_request_id": None,
        }

    def test_to_dict_returns_expected_dict_populated(self) -> None:
        """ProcessingContext.to_dict() with populated values."""
        ctx = ProcessingContext(
            tool_use_id_to_block_id={"toolu_1": "block_1", "toolu_2": "block_2"},
            current_request_id="req-123",
        )
        result = ctx.to_dict()
        assert result == {
            "tool_use_id_to_block_id": {"toolu_1": "block_1", "toolu_2": "block_2"},
            "current_request_id": "req-123",
        }

    def test_from_dict_reconstructs_object(self) -> None:
        """ProcessingContext.from_dict() reconstructs the object."""
        data = {
            "tool_use_id_to_block_id": {"toolu_a": "block_a"},
            "current_request_id": "req-abc",
        }
        ctx = ProcessingContext.from_dict(data)
        assert ctx.tool_use_id_to_block_id == {"toolu_a": "block_a"}
        assert ctx.current_request_id == "req-abc"

    def test_from_dict_with_missing_optional_fields(self) -> None:
        """ProcessingContext.from_dict() uses defaults for missing fields."""
        data = {}
        ctx = ProcessingContext.from_dict(data)
        assert ctx.tool_use_id_to_block_id == {}
        assert ctx.current_request_id is None

    def test_from_dict_with_partial_fields(self) -> None:
        """ProcessingContext.from_dict() handles partial data."""
        data = {"current_request_id": "req-only"}
        ctx = ProcessingContext.from_dict(data)
        assert ctx.tool_use_id_to_block_id == {}
        assert ctx.current_request_id == "req-only"

    def test_round_trip_empty(self) -> None:
        """Round-trip with empty context."""
        original = ProcessingContext()
        restored = ProcessingContext.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_populated(self) -> None:
        """Round-trip with populated context."""
        original = ProcessingContext(
            tool_use_id_to_block_id={
                "toolu_1": "block_1",
                "toolu_2": "block_2",
                "toolu_3": "block_3",
            },
            current_request_id="req-xyz",
        )
        restored = ProcessingContext.from_dict(original.to_dict())
        assert restored == original
