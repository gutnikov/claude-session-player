"""Tests for render function dispatch and state mutation."""

from __future__ import annotations

from claude_session_player.models import AssistantText, ScreenState, SystemOutput, UserMessage
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

    def test_unhandled_types_pass(self, empty_state: ScreenState, tool_use_line: dict) -> None:
        """Unhandled types (e.g., TOOL_USE) don't crash and don't add elements."""
        result = render(empty_state, tool_use_line)
        assert result is empty_state
        assert len(result.elements) == 0
