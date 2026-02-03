"""Tests for render function dispatch and state mutation."""

from __future__ import annotations

from claude_session_player.models import AssistantText, ScreenState, SystemOutput, ToolCall, UserMessage
from claude_session_player.renderer import render


class TestRenderUserInput:
    """Tests for rendering user input messages."""

    def test_single_line(self, empty_state: ScreenState, user_input_line: dict) -> None:
        result = render(empty_state, user_input_line)
        assert len(result.elements) == 1
        assert isinstance(result.elements[0], UserMessage)
        assert result.elements[0].text == "❯ hello world"

    def test_multiline(self, empty_state: ScreenState, user_input_multiline_line: dict) -> None:
        result = render(empty_state, user_input_multiline_line)
        assert isinstance(result.elements[0], UserMessage)
        assert result.elements[0].text == "❯ line one\n  line two\n  line three"

    def test_empty_content(self, empty_state: ScreenState) -> None:
        line = {
            "type": "user",
            "isMeta": False,
            "message": {"role": "user", "content": ""},
        }
        result = render(empty_state, line)
        assert len(result.elements) == 1
        assert result.elements[0].text == "❯"

    def test_special_chars(self, empty_state: ScreenState) -> None:
        line = {
            "type": "user",
            "isMeta": False,
            "message": {"role": "user", "content": "**bold** `code` <tag> ñ 日本語"},
        }
        result = render(empty_state, line)
        assert result.elements[0].text == "❯ **bold** `code` <tag> ñ 日本語"


class TestRenderLocalCommand:
    """Tests for rendering local command output."""

    def test_local_command_output(
        self, empty_state: ScreenState, local_command_output_line: dict
    ) -> None:
        result = render(empty_state, local_command_output_line)
        assert len(result.elements) == 1
        assert isinstance(result.elements[0], SystemOutput)
        assert result.elements[0].text == "git status output here"


class TestRenderInvisible:
    """Tests for invisible message handling."""

    def test_invisible_no_change(self, empty_state: ScreenState, user_meta_line: dict) -> None:
        result = render(empty_state, user_meta_line)
        assert len(result.elements) == 0

    def test_meta_user_invisible(self, empty_state: ScreenState) -> None:
        line = {
            "type": "user",
            "isMeta": True,
            "message": {"role": "user", "content": "skill expansion"},
        }
        result = render(empty_state, line)
        assert len(result.elements) == 0

    def test_file_history_invisible(
        self, empty_state: ScreenState, file_history_snapshot_line: dict
    ) -> None:
        result = render(empty_state, file_history_snapshot_line)
        assert len(result.elements) == 0


class TestStateMutation:
    """Tests for state mutation behavior."""

    def test_returns_same_object(self, empty_state: ScreenState, user_input_line: dict) -> None:
        result = render(empty_state, user_input_line)
        assert result is empty_state

    def test_elements_grow_by_one(
        self, empty_state: ScreenState, user_input_line: dict
    ) -> None:
        assert len(empty_state.elements) == 0
        render(empty_state, user_input_line)
        assert len(empty_state.elements) == 1

    def test_request_id_reset(self, user_input_line: dict) -> None:
        state = ScreenState(current_request_id="req_old")
        render(state, user_input_line)
        assert state.current_request_id is None


class TestRenderAssistantText:
    """Tests for rendering assistant text blocks."""

    def test_single_line_text(self, empty_state: ScreenState, assistant_text_line: dict) -> None:
        result = render(empty_state, assistant_text_line)
        assert len(result.elements) == 1
        assert isinstance(result.elements[0], AssistantText)
        assert result.elements[0].text == "● Here is my response."

    def test_request_id_set(self, empty_state: ScreenState, assistant_text_line: dict) -> None:
        render(empty_state, assistant_text_line)
        assert empty_state.current_request_id == "req_001"

    def test_request_id_on_element(
        self, empty_state: ScreenState, assistant_text_line: dict
    ) -> None:
        render(empty_state, assistant_text_line)
        assert empty_state.elements[0].request_id == "req_001"

    def test_multiline_text(self, empty_state: ScreenState) -> None:
        line = {
            "type": "assistant",
            "requestId": "req_002",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "line one\nline two\nline three"}],
            },
        }
        render(empty_state, line)
        assert empty_state.elements[0].text == "● line one\n  line two\n  line three"

    def test_empty_text(self, empty_state: ScreenState) -> None:
        line = {
            "type": "assistant",
            "requestId": "req_003",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": ""}],
            },
        }
        render(empty_state, line)
        assert empty_state.elements[0].text == "●"

    def test_markdown_passthrough(self, empty_state: ScreenState) -> None:
        line = {
            "type": "assistant",
            "requestId": "req_004",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "**bold** and `code`"}],
            },
        }
        render(empty_state, line)
        assert empty_state.elements[0].text == "● **bold** and `code`"

    def test_same_request_id_continuation(self, empty_state: ScreenState) -> None:
        """Two blocks with same requestId share current_request_id."""
        line1 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "part 1"}],
            },
        }
        line2 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "part 2"}],
            },
        }
        render(empty_state, line1)
        render(empty_state, line2)
        assert len(empty_state.elements) == 2
        assert empty_state.elements[0].request_id == "req_001"
        assert empty_state.elements[1].request_id == "req_001"
        assert empty_state.current_request_id == "req_001"

    def test_request_id_reset_by_user_input(self, empty_state: ScreenState) -> None:
        """User input between assistant blocks resets current_request_id."""
        assistant_line = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "response"}],
            },
        }
        user_line = {
            "type": "user",
            "isMeta": False,
            "message": {"role": "user", "content": "next question"},
        }
        render(empty_state, assistant_line)
        assert empty_state.current_request_id == "req_001"
        render(empty_state, user_line)
        assert empty_state.current_request_id is None


class TestRenderAssistantTextIntegration:
    """Integration tests for assistant text rendering with to_markdown."""

    def test_user_then_assistant_markdown(self, empty_state: ScreenState) -> None:
        """User → assistant produces correct markdown with blank line."""
        user_line = {
            "type": "user",
            "isMeta": False,
            "message": {"role": "user", "content": "hello"},
        }
        assistant_line = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "world"}],
            },
        }
        render(empty_state, user_line)
        render(empty_state, assistant_line)
        md = empty_state.to_markdown()
        assert md == "❯ hello\n\n● world"

    def test_two_assistant_same_rid_markdown(self, empty_state: ScreenState) -> None:
        """Two assistant blocks with same requestId: no blank line in markdown."""
        line1 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "first"}],
            },
        }
        line2 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "second"}],
            },
        }
        render(empty_state, line1)
        render(empty_state, line2)
        md = empty_state.to_markdown()
        assert md == "● first\n● second"

    def test_full_conversation_markdown(self, empty_state: ScreenState) -> None:
        """User → assistant(req_1) → assistant(req_1) → user → assistant(req_2)."""
        lines = [
            {
                "type": "user",
                "isMeta": False,
                "message": {"role": "user", "content": "question 1"},
            },
            {
                "type": "assistant",
                "requestId": "req_001",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "answer part 1"}],
                },
            },
            {
                "type": "assistant",
                "requestId": "req_001",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "answer part 2"}],
                },
            },
            {
                "type": "user",
                "isMeta": False,
                "message": {"role": "user", "content": "question 2"},
            },
            {
                "type": "assistant",
                "requestId": "req_002",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "answer 2"}],
                },
            },
        ]
        for line in lines:
            render(empty_state, line)
        md = empty_state.to_markdown()
        expected = "❯ question 1\n\n● answer part 1\n● answer part 2\n\n❯ question 2\n\n● answer 2"
        assert md == expected


class TestRenderIntegration:
    """Mini integration tests for render dispatch."""

    def test_invisible_user_invisible(
        self,
        empty_state: ScreenState,
        file_history_snapshot_line: dict,
        user_input_line: dict,
        summary_line: dict,
    ) -> None:
        """Feed invisible, user input, invisible → 1 element."""
        render(empty_state, file_history_snapshot_line)
        render(empty_state, user_input_line)
        render(empty_state, summary_line)
        assert len(empty_state.elements) == 1

    def test_user_plus_local_command(
        self,
        empty_state: ScreenState,
        user_input_line: dict,
        local_command_output_line: dict,
    ) -> None:
        """User input + local command → 2 elements, correct markdown."""
        render(empty_state, user_input_line)
        render(empty_state, local_command_output_line)
        assert len(empty_state.elements) == 2
        md = empty_state.to_markdown()
        assert "❯ hello world" in md
        assert "git status output here" in md

    def test_unhandled_types_pass(self, empty_state: ScreenState, thinking_line: dict) -> None:
        """Unhandled types (e.g., THINKING) don't crash and don't add elements."""
        result = render(empty_state, thinking_line)
        assert result is empty_state
        assert len(result.elements) == 0


class TestRenderToolUse:
    """Tests for rendering tool_use assistant blocks."""

    def test_single_tool_use(self, empty_state: ScreenState, tool_use_line: dict) -> None:
        result = render(empty_state, tool_use_line)
        assert len(result.elements) == 1
        assert isinstance(result.elements[0], ToolCall)
        assert result.elements[0].tool_name == "Bash"
        assert result.elements[0].label == "List files"

    def test_tool_use_id_stored(self, empty_state: ScreenState, tool_use_line: dict) -> None:
        render(empty_state, tool_use_line)
        assert empty_state.elements[0].tool_use_id == "toolu_001"

    def test_tool_call_registered(self, empty_state: ScreenState, tool_use_line: dict) -> None:
        render(empty_state, tool_use_line)
        assert "toolu_001" in empty_state.tool_calls
        assert empty_state.tool_calls["toolu_001"] == 0

    def test_request_id_set(self, empty_state: ScreenState, tool_use_line: dict) -> None:
        render(empty_state, tool_use_line)
        assert empty_state.current_request_id == "req_001"
        assert empty_state.elements[0].request_id == "req_001"

    def test_read_tool_basename(self, empty_state: ScreenState, tool_use_read_line: dict) -> None:
        render(empty_state, tool_use_read_line)
        assert empty_state.elements[0].label == "main.py"

    def test_write_tool_basename(self, empty_state: ScreenState, tool_use_write_line: dict) -> None:
        render(empty_state, tool_use_write_line)
        assert empty_state.elements[0].label == "config.py"

    def test_tool_call_index_after_other_elements(self, empty_state: ScreenState) -> None:
        """Tool call registered at correct index when other elements precede it."""
        user_line = {
            "type": "user",
            "isMeta": False,
            "message": {"role": "user", "content": "hello"},
        }
        tool_line = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_099", "name": "Bash", "input": {"command": "ls"}}],
            },
        }
        render(empty_state, user_line)
        render(empty_state, tool_line)
        assert empty_state.tool_calls["toolu_099"] == 1

    def test_markdown_output(self, empty_state: ScreenState, tool_use_line: dict) -> None:
        render(empty_state, tool_use_line)
        md = empty_state.to_markdown()
        assert md == "\u25cf Bash(List files)"


class TestRenderToolUseParallel:
    """Tests for parallel tool calls with same requestId."""

    def test_two_parallel_tools_no_blank_line(self, empty_state: ScreenState) -> None:
        """Two tool_use blocks with same requestId → no blank line between."""
        line1 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_A", "name": "Bash", "input": {"command": "ls"}}],
            },
        }
        line2 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_B", "name": "Read", "input": {"file_path": "/a/b.py"}}],
            },
        }
        render(empty_state, line1)
        render(empty_state, line2)
        assert len(empty_state.elements) == 2
        assert empty_state.tool_calls["toolu_A"] == 0
        assert empty_state.tool_calls["toolu_B"] == 1
        md = empty_state.to_markdown()
        assert md == "\u25cf Bash(ls)\n\u25cf Read(b.py)"

    def test_text_then_tool_same_rid_no_blank(self, empty_state: ScreenState) -> None:
        """AssistantText then tool_use with same requestId → no blank line."""
        text_line = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Let me check."}],
            },
        }
        tool_line = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_C", "name": "Bash", "input": {"command": "ls"}}],
            },
        }
        render(empty_state, text_line)
        render(empty_state, tool_line)
        md = empty_state.to_markdown()
        assert md == "\u25cf Let me check.\n\u25cf Bash(ls)"

    def test_tool_use_new_rid_blank_line(self, empty_state: ScreenState) -> None:
        """Tool_use with new requestId after previous → blank line."""
        line1 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_D", "name": "Bash", "input": {"command": "ls"}}],
            },
        }
        line2 = {
            "type": "assistant",
            "requestId": "req_002",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_E", "name": "Read", "input": {"file_path": "/x.py"}}],
            },
        }
        render(empty_state, line1)
        render(empty_state, line2)
        md = empty_state.to_markdown()
        assert md == "\u25cf Bash(ls)\n\n\u25cf Read(x.py)"


class TestRenderToolUseMarkdown:
    """Tests for ToolCall markdown output format."""

    def test_tool_call_without_result(self, empty_state: ScreenState, tool_use_line: dict) -> None:
        render(empty_state, tool_use_line)
        md = empty_state.to_markdown()
        assert md == "\u25cf Bash(List files)"
        assert "\u2514" not in md

    def test_tool_call_with_result(self) -> None:
        """Preview: tool call with result set produces └ line with proper indentation."""
        from claude_session_player.formatter import format_element

        tc = ToolCall(tool_name="Bash", tool_use_id="t1", label="ls", result="file1.py\nfile2.py")
        formatted = format_element(tc)
        assert "\u25cf Bash(ls)" in formatted
        assert "  \u2514 file1.py" in formatted
        assert "    file2.py" in formatted

    def test_tool_call_with_error_result(self) -> None:
        """Preview: tool call with error result produces ✗ line."""
        from claude_session_player.formatter import format_element

        tc = ToolCall(tool_name="Bash", tool_use_id="t1", label="bad", result="not found", is_error=True)
        formatted = format_element(tc)
        assert "\u25cf Bash(bad)" in formatted
        assert "  \u2717 not found" in formatted

    def test_tool_call_with_progress(self) -> None:
        """Preview: tool call with progress_text produces └ line."""
        from claude_session_player.formatter import format_element

        tc = ToolCall(tool_name="Bash", tool_use_id="t1", label="running", progress_text="50%")
        formatted = format_element(tc)
        assert "\u25cf Bash(running)" in formatted
        assert "  \u2514 50%" in formatted

    def test_user_then_tool_call_markdown(self, empty_state: ScreenState) -> None:
        """User → tool call produces correct markdown spacing."""
        user_line = {
            "type": "user",
            "isMeta": False,
            "message": {"role": "user", "content": "do something"},
        }
        tool_line = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_F", "name": "Bash", "input": {"command": "echo hi"}}],
            },
        }
        render(empty_state, user_line)
        render(empty_state, tool_line)
        md = empty_state.to_markdown()
        assert md == "\u276f do something\n\n\u25cf Bash(echo hi)"


class TestRenderToolResult:
    """Tests for rendering tool_result user messages."""

    def test_result_matches_existing_tool_call(
        self, empty_state: ScreenState, tool_use_line: dict, tool_result_line: dict
    ) -> None:
        """Tool result matches existing tool call → result field updated."""
        render(empty_state, tool_use_line)
        render(empty_state, tool_result_line)
        # No new element added; existing ToolCall updated
        assert len(empty_state.elements) == 1
        element = empty_state.elements[0]
        assert isinstance(element, ToolCall)
        assert element.result == "file1.py\nfile2.py"
        assert element.is_error is False

    def test_result_with_is_error_true(
        self, empty_state: ScreenState, tool_result_error_line: dict
    ) -> None:
        """Tool result with is_error=true → is_error flag set on ToolCall."""
        # First create a tool call with matching id
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_002", "name": "Bash", "input": {"command": "foo"}}],
            },
        }
        render(empty_state, tool_use)
        render(empty_state, tool_result_error_line)
        element = empty_state.elements[0]
        assert isinstance(element, ToolCall)
        assert element.result == "command not found: foo"
        assert element.is_error is True

    def test_result_unknown_tool_use_id_creates_system_output(self, empty_state: ScreenState) -> None:
        """Tool result with unknown tool_use_id → rendered as SystemOutput."""
        orphan_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "unknown_tool_id",
                        "content": "orphan result text",
                        "is_error": False,
                    }
                ],
            },
        }
        render(empty_state, orphan_result)
        assert len(empty_state.elements) == 1
        element = empty_state.elements[0]
        assert isinstance(element, SystemOutput)
        assert element.text == "orphan result text"

    def test_result_resets_current_request_id(
        self, empty_state: ScreenState, tool_use_line: dict, tool_result_line: dict
    ) -> None:
        """Tool result resets current_request_id to None."""
        render(empty_state, tool_use_line)
        assert empty_state.current_request_id == "req_001"
        render(empty_state, tool_result_line)
        assert empty_state.current_request_id is None

    def test_multiple_sequential_results_matched_correctly(self, empty_state: ScreenState) -> None:
        """Multiple sequential tool results for different tool calls → each matched correctly."""
        tool_use_1 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_A", "name": "Bash", "input": {"command": "ls"}}],
            },
        }
        tool_use_2 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_B", "name": "Read", "input": {"file_path": "/a.py"}}],
            },
        }
        result_1 = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "output A", "is_error": False}],
            },
        }
        result_2 = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_B", "content": "output B", "is_error": False}],
            },
        }
        render(empty_state, tool_use_1)
        render(empty_state, tool_use_2)
        render(empty_state, result_1)
        render(empty_state, result_2)

        assert len(empty_state.elements) == 2
        assert empty_state.elements[0].result == "output A"
        assert empty_state.elements[1].result == "output B"


class TestRenderToolResultTruncation:
    """Tests for tool result truncation."""

    def test_short_result_not_truncated(self, empty_state: ScreenState) -> None:
        """Short result (1-5 lines) → not truncated."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_001", "name": "Bash", "input": {"command": "ls"}}],
            },
        }
        tool_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "line1\nline2\nline3\nline4\nline5",
                        "is_error": False,
                    }
                ],
            },
        }
        render(empty_state, tool_use)
        render(empty_state, tool_result)
        assert empty_state.elements[0].result == "line1\nline2\nline3\nline4\nline5"

    def test_long_result_truncated(self, empty_state: ScreenState) -> None:
        """Long result (>5 lines) → truncated to 4 lines + …."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_001", "name": "Bash", "input": {"command": "ls"}}],
            },
        }
        tool_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "line1\nline2\nline3\nline4\nline5\nline6\nline7",
                        "is_error": False,
                    }
                ],
            },
        }
        render(empty_state, tool_use)
        render(empty_state, tool_result)
        assert empty_state.elements[0].result == "line1\nline2\nline3\nline4\n…"

    def test_empty_result_shows_no_output(self, empty_state: ScreenState) -> None:
        """Empty result → '(no output)'."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_001", "name": "Bash", "input": {"command": "ls"}}],
            },
        }
        tool_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "",
                        "is_error": False,
                    }
                ],
            },
        }
        render(empty_state, tool_use)
        render(empty_state, tool_result)
        assert empty_state.elements[0].result == "(no output)"

    def test_single_line_result(self, empty_state: ScreenState) -> None:
        """Single-line result → single line."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_001", "name": "Bash", "input": {"command": "echo hi"}}],
            },
        }
        tool_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "hi",
                        "is_error": False,
                    }
                ],
            },
        }
        render(empty_state, tool_use)
        render(empty_state, tool_result)
        assert empty_state.elements[0].result == "hi"


class TestRenderToolResultMarkdown:
    """Tests for tool result markdown output."""

    def test_tool_call_plus_success_result_markdown(self, empty_state: ScreenState) -> None:
        """Tool call + success result → ● Tool(label)\\n  └ output."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_001", "name": "Bash", "input": {"description": "List files"}}],
            },
        }
        tool_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "file.txt",
                        "is_error": False,
                    }
                ],
            },
        }
        render(empty_state, tool_use)
        render(empty_state, tool_result)
        md = empty_state.to_markdown()
        assert md == "\u25cf Bash(List files)\n  \u2514 file.txt"

    def test_tool_call_plus_error_result_markdown(self, empty_state: ScreenState) -> None:
        """Tool call + error result → ● Tool(label)\\n  ✗ error message."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_001", "name": "Bash", "input": {"description": "Bad command"}}],
            },
        }
        tool_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "command not found",
                        "is_error": True,
                    }
                ],
            },
        }
        render(empty_state, tool_use)
        render(empty_state, tool_result)
        md = empty_state.to_markdown()
        assert md == "\u25cf Bash(Bad command)\n  \u2717 command not found"

    def test_tool_call_plus_multiline_result_markdown(self, empty_state: ScreenState) -> None:
        """Tool call + multi-line result → proper indentation."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_001", "name": "Bash", "input": {"description": "Git status"}}],
            },
        }
        tool_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "On branch main\nYour branch is up to date",
                        "is_error": False,
                    }
                ],
            },
        }
        render(empty_state, tool_use)
        render(empty_state, tool_result)
        md = empty_state.to_markdown()
        expected = "\u25cf Bash(Git status)\n  \u2514 On branch main\n    Your branch is up to date"
        assert md == expected

    def test_tool_call_plus_truncated_result_markdown(self, empty_state: ScreenState) -> None:
        """Tool call + truncated result → … on last line."""
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_001", "name": "Bash", "input": {"description": "Long output"}}],
            },
        }
        tool_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "1\n2\n3\n4\n5\n6\n7",
                        "is_error": False,
                    }
                ],
            },
        }
        render(empty_state, tool_use)
        render(empty_state, tool_result)
        md = empty_state.to_markdown()
        expected = "\u25cf Bash(Long output)\n  \u2514 1\n    2\n    3\n    4\n    …"
        assert md == expected

    def test_parallel_tool_calls_with_results_markdown(self, empty_state: ScreenState) -> None:
        """Parallel tool calls + their results → all matched, all rendered correctly."""
        tool_use_1 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_A", "name": "Bash", "input": {"description": "cmd A"}}],
            },
        }
        tool_use_2 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_B", "name": "Read", "input": {"file_path": "/a.py"}}],
            },
        }
        result_1 = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "result A", "is_error": False}],
            },
        }
        result_2 = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_B", "content": "result B", "is_error": False}],
            },
        }
        render(empty_state, tool_use_1)
        render(empty_state, tool_use_2)
        render(empty_state, result_1)
        render(empty_state, result_2)
        md = empty_state.to_markdown()
        expected = "\u25cf Bash(cmd A)\n  \u2514 result A\n\u25cf Read(a.py)\n  \u2514 result B"
        assert md == expected


class TestRenderToolResultFullFlow:
    """Full flow integration tests for tool results."""

    def test_user_input_to_tool_use_to_result_markdown(self, empty_state: ScreenState) -> None:
        """User input → assistant tool_use → tool_result → correct final markdown."""
        user_line = {
            "type": "user",
            "isMeta": False,
            "message": {"role": "user", "content": "run ls"},
        }
        tool_use = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_001", "name": "Bash", "input": {"description": "List files"}}],
            },
        }
        tool_result = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_001",
                        "content": "file.txt\ndir/",
                        "is_error": False,
                    }
                ],
            },
        }
        render(empty_state, user_line)
        render(empty_state, tool_use)
        render(empty_state, tool_result)
        md = empty_state.to_markdown()
        expected = "\u276f run ls\n\n\u25cf Bash(List files)\n  \u2514 file.txt\n    dir/"
        assert md == expected

    def test_two_parallel_tool_uses_two_results_all_matched(self, empty_state: ScreenState) -> None:
        """User → 2 parallel tool_uses → 2 tool_results → all matched, all rendered."""
        user_line = {
            "type": "user",
            "isMeta": False,
            "message": {"role": "user", "content": "check both"},
        }
        tool_use_1 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_X", "name": "Bash", "input": {"description": "cmd X"}}],
            },
        }
        tool_use_2 = {
            "type": "assistant",
            "requestId": "req_001",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_Y", "name": "Bash", "input": {"description": "cmd Y"}}],
            },
        }
        result_1 = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_X", "content": "X output", "is_error": False}],
            },
        }
        result_2 = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_Y", "content": "Y output", "is_error": False}],
            },
        }
        render(empty_state, user_line)
        render(empty_state, tool_use_1)
        render(empty_state, tool_use_2)
        render(empty_state, result_1)
        render(empty_state, result_2)

        md = empty_state.to_markdown()
        # Tool calls grouped (same request_id), then results update in place
        expected = (
            "\u276f check both\n\n"
            "\u25cf Bash(cmd X)\n  \u2514 X output\n"
            "\u25cf Bash(cmd Y)\n  \u2514 Y output"
        )
        assert md == expected
