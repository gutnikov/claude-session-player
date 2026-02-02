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
        """Preview: tool call with result set produces └ line."""
        from claude_session_player.formatter import format_element

        tc = ToolCall(tool_name="Bash", tool_use_id="t1", label="ls", result="file1.py\nfile2.py")
        formatted = format_element(tc)
        assert "\u25cf Bash(ls)" in formatted
        assert "  \u2514 file1.py\nfile2.py" in formatted

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
