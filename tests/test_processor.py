"""Tests for the event processor."""

import pytest

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
from claude_session_player.processor import (
    _clear_tool_content_cache,
    _tool_content_cache,
    process_line,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the tool content cache before each test."""
    _clear_tool_content_cache()
    yield
    _clear_tool_content_cache()


@pytest.fixture
def context() -> ProcessingContext:
    """Return a fresh ProcessingContext."""
    return ProcessingContext()


class TestUserInput:
    """Tests for USER_INPUT line type."""

    def test_user_input_creates_add_block_user(
        self, context: ProcessingContext, user_input_line: dict
    ) -> None:
        """USER_INPUT → AddBlock(USER)."""
        events = process_line(context, user_input_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.USER
        assert isinstance(event.block.content, UserContent)
        assert event.block.content.text == "hello world"

    def test_user_input_resets_request_id(
        self, context: ProcessingContext, user_input_line: dict
    ) -> None:
        """USER_INPUT resets context.current_request_id to None."""
        context.current_request_id = "some-req-id"
        process_line(context, user_input_line)
        assert context.current_request_id is None

    def test_user_input_multiline(
        self, context: ProcessingContext, user_input_multiline_line: dict
    ) -> None:
        """USER_INPUT with multiline content preserves text."""
        events = process_line(context, user_input_multiline_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.content.text == "line one\nline two\nline three"


class TestLocalCommandOutput:
    """Tests for LOCAL_COMMAND_OUTPUT line type."""

    def test_local_command_creates_add_block_system(
        self, context: ProcessingContext, local_command_output_line: dict
    ) -> None:
        """LOCAL_COMMAND_OUTPUT → AddBlock(SYSTEM)."""
        events = process_line(context, local_command_output_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.SYSTEM
        assert isinstance(event.block.content, SystemContent)
        assert event.block.content.text == "git status output here"


class TestAssistantText:
    """Tests for ASSISTANT_TEXT line type."""

    def test_assistant_text_creates_add_block_assistant(
        self, context: ProcessingContext, assistant_text_line: dict
    ) -> None:
        """ASSISTANT_TEXT → AddBlock(ASSISTANT)."""
        events = process_line(context, assistant_text_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.ASSISTANT
        assert isinstance(event.block.content, AssistantContent)
        assert event.block.content.text == "Here is my response."

    def test_assistant_text_updates_request_id(
        self, context: ProcessingContext, assistant_text_line: dict
    ) -> None:
        """ASSISTANT_TEXT updates context.current_request_id."""
        events = process_line(context, assistant_text_line)

        assert context.current_request_id == "req_001"
        assert events[0].block.request_id == "req_001"


class TestToolUse:
    """Tests for TOOL_USE line type."""

    def test_tool_use_creates_add_block_tool_call(
        self, context: ProcessingContext, tool_use_line: dict
    ) -> None:
        """TOOL_USE → AddBlock(TOOL_CALL)."""
        events = process_line(context, tool_use_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.TOOL_CALL
        assert isinstance(event.block.content, ToolCallContent)
        assert event.block.content.tool_name == "Bash"
        assert event.block.content.tool_use_id == "toolu_001"
        assert event.block.content.label == "List files"

    def test_tool_use_updates_context_mapping(
        self, context: ProcessingContext, tool_use_line: dict
    ) -> None:
        """TOOL_USE updates context.tool_use_id_to_block_id mapping."""
        events = process_line(context, tool_use_line)

        block_id = events[0].block.id
        assert context.tool_use_id_to_block_id["toolu_001"] == block_id

    def test_tool_use_updates_request_id(
        self, context: ProcessingContext, tool_use_line: dict
    ) -> None:
        """TOOL_USE updates context.current_request_id."""
        process_line(context, tool_use_line)
        assert context.current_request_id == "req_001"


class TestThinking:
    """Tests for THINKING line type."""

    def test_thinking_creates_add_block_thinking(
        self, context: ProcessingContext, thinking_line: dict
    ) -> None:
        """THINKING → AddBlock(THINKING)."""
        events = process_line(context, thinking_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.THINKING
        assert isinstance(event.block.content, ThinkingContent)

    def test_thinking_updates_request_id(
        self, context: ProcessingContext, thinking_line: dict
    ) -> None:
        """THINKING updates context.current_request_id."""
        events = process_line(context, thinking_line)

        assert context.current_request_id == "req_001"
        assert events[0].block.request_id == "req_001"


class TestTurnDuration:
    """Tests for TURN_DURATION line type."""

    def test_turn_duration_creates_add_block_duration(
        self, context: ProcessingContext, turn_duration_line: dict
    ) -> None:
        """TURN_DURATION → AddBlock(DURATION)."""
        events = process_line(context, turn_duration_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.DURATION
        assert isinstance(event.block.content, DurationContent)
        assert event.block.content.duration_ms == 12500

    def test_turn_duration_resets_request_id(
        self, context: ProcessingContext, turn_duration_line: dict
    ) -> None:
        """TURN_DURATION resets context.current_request_id to None."""
        context.current_request_id = "some-req-id"
        process_line(context, turn_duration_line)
        assert context.current_request_id is None


class TestToolResult:
    """Tests for TOOL_RESULT line type."""

    def test_tool_result_with_match_creates_update_block(
        self, context: ProcessingContext, tool_use_line: dict, tool_result_line: dict
    ) -> None:
        """TOOL_RESULT with matching tool_use_id → UpdateBlock."""
        # First create the tool use
        events1 = process_line(context, tool_use_line)
        block_id = events1[0].block.id

        # Then process the result
        events2 = process_line(context, tool_result_line)

        assert len(events2) == 1
        event = events2[0]
        assert isinstance(event, UpdateBlock)
        assert event.block_id == block_id
        assert isinstance(event.content, ToolCallContent)
        assert event.content.result == "file1.py\nfile2.py"
        assert event.content.is_error is False

    def test_tool_result_error_flag(
        self, context: ProcessingContext, tool_use_line: dict
    ) -> None:
        """TOOL_RESULT with is_error=True sets is_error on UpdateBlock."""
        # Modify tool_use_line to match the error result
        tool_use_line = {
            "type": "assistant",
            "uuid": "bbb-223",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_002",
                        "name": "Bash",
                        "input": {"command": "foo"},
                    }
                ],
            },
        }
        tool_result_error_line = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_002",
                        "content": "command not found: foo",
                        "is_error": True,
                    }
                ],
            },
        }

        process_line(context, tool_use_line)
        events = process_line(context, tool_result_error_line)

        assert len(events) == 1
        assert isinstance(events[0], UpdateBlock)
        assert events[0].content.is_error is True

    def test_tool_result_orphan_creates_add_block_system(
        self, context: ProcessingContext
    ) -> None:
        """TOOL_RESULT without matching tool_use_id → AddBlock(SYSTEM)."""
        orphan_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "unknown_tool",
                        "content": "orphan result text",
                        "is_error": False,
                    }
                ],
            },
        }

        events = process_line(context, orphan_result)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.SYSTEM
        assert isinstance(event.block.content, SystemContent)
        assert event.block.content.text == "orphan result text"


class TestProgressMessages:
    """Tests for progress message line types."""

    def test_bash_progress_with_match_creates_update_block(
        self, context: ProcessingContext, tool_use_line: dict, bash_progress_line: dict
    ) -> None:
        """BASH_PROGRESS with matching parent → UpdateBlock."""
        events1 = process_line(context, tool_use_line)
        block_id = events1[0].block.id

        events2 = process_line(context, bash_progress_line)

        assert len(events2) == 1
        event = events2[0]
        assert isinstance(event, UpdateBlock)
        assert event.block_id == block_id
        assert isinstance(event.content, ToolCallContent)
        assert event.content.progress_text == "Step 1/12: FROM python:3.11-slim"

    def test_hook_progress_with_match_creates_update_block(
        self, context: ProcessingContext
    ) -> None:
        """HOOK_PROGRESS with matching parent → UpdateBlock."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_002",
                        "name": "Read",
                        "input": {"file_path": "/foo/bar.py"},
                    }
                ],
            },
        }
        hook_progress = {
            "type": "progress",
            "data": {
                "type": "hook_progress",
                "hookEvent": "PostToolUse",
                "hookName": "PostToolUse:Read",
            },
            "parentToolUseID": "toolu_002",
        }

        events1 = process_line(context, tool_use)
        block_id = events1[0].block.id

        events2 = process_line(context, hook_progress)

        assert len(events2) == 1
        assert isinstance(events2[0], UpdateBlock)
        assert events2[0].block_id == block_id
        assert events2[0].content.progress_text == "Hook: PostToolUse:Read"

    def test_agent_progress_with_match_creates_update_block(
        self, context: ProcessingContext
    ) -> None:
        """AGENT_PROGRESS with matching parent → UpdateBlock."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_003",
                        "name": "Task",
                        "input": {"description": "Explore"},
                    }
                ],
            },
        }
        agent_progress = {
            "type": "progress",
            "data": {"type": "agent_progress"},
            "parentToolUseID": "toolu_003",
        }

        events1 = process_line(context, tool_use)
        block_id = events1[0].block.id

        events2 = process_line(context, agent_progress)

        assert len(events2) == 1
        assert isinstance(events2[0], UpdateBlock)
        assert events2[0].block_id == block_id
        assert events2[0].content.progress_text == "Agent: working…"

    def test_query_update_with_match_creates_update_block(
        self, context: ProcessingContext
    ) -> None:
        """QUERY_UPDATE with matching parent → UpdateBlock."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_004",
                        "name": "WebSearch",
                        "input": {"query": "test query"},
                    }
                ],
            },
        }
        query_update = {
            "type": "progress",
            "data": {"type": "query_update", "query": "Claude hooks 2026"},
            "parentToolUseID": "toolu_004",
        }

        events1 = process_line(context, tool_use)
        block_id = events1[0].block.id

        events2 = process_line(context, query_update)

        assert len(events2) == 1
        assert isinstance(events2[0], UpdateBlock)
        assert events2[0].block_id == block_id
        assert events2[0].content.progress_text == "Searching: Claude hooks 2026"

    def test_search_results_with_match_creates_update_block(
        self, context: ProcessingContext
    ) -> None:
        """SEARCH_RESULTS with matching parent → UpdateBlock."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_004",
                        "name": "WebSearch",
                        "input": {"query": "test"},
                    }
                ],
            },
        }
        search_results = {
            "type": "progress",
            "data": {"type": "search_results_received", "resultCount": 10},
            "parentToolUseID": "toolu_004",
        }

        events1 = process_line(context, tool_use)
        block_id = events1[0].block.id

        events2 = process_line(context, search_results)

        assert len(events2) == 1
        assert isinstance(events2[0], UpdateBlock)
        assert events2[0].block_id == block_id
        assert events2[0].content.progress_text == "10 results"

    def test_waiting_for_task_with_match_creates_update_block(
        self, context: ProcessingContext, waiting_for_task_line: dict
    ) -> None:
        """WAITING_FOR_TASK with matching parent → UpdateBlock."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_005",
                        "name": "Task",
                        "input": {"description": "Debug"},
                    }
                ],
            },
        }

        events1 = process_line(context, tool_use)
        block_id = events1[0].block.id

        events2 = process_line(context, waiting_for_task_line)

        assert len(events2) == 1
        assert isinstance(events2[0], UpdateBlock)
        assert events2[0].block_id == block_id
        assert "Waiting:" in events2[0].content.progress_text

    def test_waiting_for_task_without_match_creates_add_block_system(
        self, context: ProcessingContext, waiting_for_task_no_parent_line: dict
    ) -> None:
        """WAITING_FOR_TASK without match → AddBlock(SYSTEM)."""
        events = process_line(context, waiting_for_task_no_parent_line)

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, AddBlock)
        assert event.block.type == BlockType.SYSTEM
        assert isinstance(event.block.content, SystemContent)
        assert "Waiting:" in event.block.content.text


class TestCompactBoundary:
    """Tests for COMPACT_BOUNDARY line type."""

    def test_compact_boundary_returns_clear_all(
        self, context: ProcessingContext, compact_boundary_line: dict
    ) -> None:
        """COMPACT_BOUNDARY → ClearAll."""
        events = process_line(context, compact_boundary_line)

        assert len(events) == 1
        assert isinstance(events[0], ClearAll)

    def test_compact_boundary_clears_context(
        self, context: ProcessingContext, compact_boundary_line: dict
    ) -> None:
        """COMPACT_BOUNDARY clears context state."""
        context.tool_use_id_to_block_id["toolu_001"] = "block_001"
        context.current_request_id = "req_001"

        process_line(context, compact_boundary_line)

        assert context.tool_use_id_to_block_id == {}
        assert context.current_request_id is None


class TestInvisible:
    """Tests for INVISIBLE line type."""

    def test_invisible_returns_empty_list(
        self, context: ProcessingContext, user_meta_line: dict
    ) -> None:
        """INVISIBLE → empty list."""
        events = process_line(context, user_meta_line)
        assert events == []

    def test_sidechain_user_is_invisible(
        self, context: ProcessingContext, sidechain_user_line: dict
    ) -> None:
        """Sidechain user messages are invisible."""
        events = process_line(context, sidechain_user_line)
        assert events == []

    def test_sidechain_assistant_is_invisible(
        self, context: ProcessingContext, sidechain_assistant_line: dict
    ) -> None:
        """Sidechain assistant messages are invisible."""
        events = process_line(context, sidechain_assistant_line)
        assert events == []


class TestBlockIdGeneration:
    """Tests for block ID generation."""

    def test_block_ids_are_unique(self, context: ProcessingContext) -> None:
        """Block IDs are unique across multiple events."""
        user_line = {
            "type": "user",
            "isMeta": False,
            "message": {"role": "user", "content": "test"},
        }

        events1 = process_line(context, user_line)
        events2 = process_line(context, user_line)
        events3 = process_line(context, user_line)

        ids = {events1[0].block.id, events2[0].block.id, events3[0].block.id}
        assert len(ids) == 3, "Block IDs should be unique"

    def test_block_ids_are_valid_hex(self, context: ProcessingContext) -> None:
        """Block IDs are valid 32-character hex strings (UUID without dashes)."""
        user_line = {
            "type": "user",
            "isMeta": False,
            "message": {"role": "user", "content": "test"},
        }

        events = process_line(context, user_line)
        block_id = events[0].block.id

        assert len(block_id) == 32
        assert all(c in "0123456789abcdef" for c in block_id)


class TestToolUseIdMapping:
    """Tests for tool_use_id to block_id mapping."""

    def test_mapping_works_across_multiple_tools(
        self, context: ProcessingContext
    ) -> None:
        """Tool use ID mapping works correctly for multiple tools."""
        tool_use_1 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_A", "name": "Bash", "input": {}}
                ],
            },
        }
        tool_use_2 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_B", "name": "Read", "input": {}}
                ],
            },
        }
        result_A = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_A", "content": "A"}
                ],
            },
        }
        result_B = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_B", "content": "B"}
                ],
            },
        }

        events1 = process_line(context, tool_use_1)
        events2 = process_line(context, tool_use_2)
        block_id_A = events1[0].block.id
        block_id_B = events2[0].block.id

        events_A = process_line(context, result_A)
        events_B = process_line(context, result_B)

        assert isinstance(events_A[0], UpdateBlock)
        assert events_A[0].block_id == block_id_A
        assert events_A[0].content.result == "A"

        assert isinstance(events_B[0], UpdateBlock)
        assert events_B[0].block_id == block_id_B
        assert events_B[0].content.result == "B"


class TestRequestIdGrouping:
    """Tests for request ID grouping in sequential assistant lines."""

    def test_sequential_assistant_blocks_preserve_request_id(
        self, context: ProcessingContext
    ) -> None:
        """Sequential assistant blocks share the same request_id."""
        text_line = {
            "type": "assistant",
            "requestId": "req_shared",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "First part"}],
            },
        }
        tool_line = {
            "type": "assistant",
            "requestId": "req_shared",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_X", "name": "Bash", "input": {}}
                ],
            },
        }

        events1 = process_line(context, text_line)
        events2 = process_line(context, tool_line)

        assert events1[0].block.request_id == "req_shared"
        assert events2[0].block.request_id == "req_shared"
        assert context.current_request_id == "req_shared"


class TestProgressWithoutMatch:
    """Tests for progress messages without matching tool calls."""

    def test_bash_progress_without_match_returns_empty(
        self, context: ProcessingContext
    ) -> None:
        """BASH_PROGRESS without matching tool call returns empty list."""
        bash_progress = {
            "type": "progress",
            "data": {"type": "bash_progress", "fullOutput": "output"},
            "parentToolUseID": "unknown_tool",
        }

        events = process_line(context, bash_progress)
        assert events == []

    def test_hook_progress_without_match_returns_empty(
        self, context: ProcessingContext
    ) -> None:
        """HOOK_PROGRESS without matching tool call returns empty list."""
        hook_progress = {
            "type": "progress",
            "data": {"type": "hook_progress", "hookName": "test"},
            "parentToolUseID": "unknown_tool",
        }

        events = process_line(context, hook_progress)
        assert events == []

    def test_agent_progress_without_match_returns_empty(
        self, context: ProcessingContext
    ) -> None:
        """AGENT_PROGRESS without matching tool call returns empty list."""
        agent_progress = {
            "type": "progress",
            "data": {"type": "agent_progress"},
            "parentToolUseID": "unknown_tool",
        }

        events = process_line(context, agent_progress)
        assert events == []
