"""Tests for formatting helpers and to_markdown output."""

from __future__ import annotations

from claude_session_player.formatter import (
    format_assistant_text,
    format_element,
    format_user_text,
    to_markdown,
    truncate_result,
)
from claude_session_player.models import (
    AssistantText,
    ScreenState,
    SystemOutput,
    ThinkingIndicator,
    ToolCall,
    UserMessage,
)


class TestTruncateResult:
    """Tests for truncate_result."""

    def test_empty_returns_no_output(self) -> None:
        assert truncate_result("") == "(no output)"

    def test_single_line_no_truncation(self) -> None:
        assert truncate_result("hello") == "hello"

    def test_five_lines_no_truncation(self) -> None:
        text = "line1\nline2\nline3\nline4\nline5"
        assert truncate_result(text) == text

    def test_six_lines_truncated(self) -> None:
        text = "line1\nline2\nline3\nline4\nline5\nline6"
        result = truncate_result(text)
        assert result == "line1\nline2\nline3\nline4\n…"

    def test_ten_lines_truncated(self) -> None:
        lines = [f"line{i}" for i in range(1, 11)]
        text = "\n".join(lines)
        result = truncate_result(text)
        assert result == "line1\nline2\nline3\nline4\n…"

    def test_custom_max_lines(self) -> None:
        text = "a\nb\nc\nd\ne"
        result = truncate_result(text, max_lines=3)
        assert result == "a\nb\n…"

    def test_whitespace_only_not_empty(self) -> None:
        # Whitespace is not falsy for this purpose
        assert truncate_result("   ") == "   "


class TestFormatUserText:
    """Tests for format_user_text."""

    def test_single_line(self) -> None:
        assert format_user_text("hello") == "❯ hello"

    def test_multiline(self) -> None:
        result = format_user_text("line one\nline two\nline three")
        assert result == "❯ line one\n  line two\n  line three"

    def test_empty_string(self) -> None:
        assert format_user_text("") == "❯"

    def test_single_newline(self) -> None:
        result = format_user_text("first\nsecond")
        assert result == "❯ first\n  second"

    def test_unicode(self) -> None:
        assert format_user_text("日本語テスト") == "❯ 日本語テスト"

    def test_markdown_chars(self) -> None:
        result = format_user_text("**bold** and `code`")
        assert result == "❯ **bold** and `code`"


class TestFormatAssistantText:
    """Tests for format_assistant_text."""

    def test_single_line(self) -> None:
        assert format_assistant_text("hello") == "● hello"

    def test_multiline(self) -> None:
        result = format_assistant_text("line one\nline two\nline three")
        assert result == "● line one\n  line two\n  line three"

    def test_empty_string(self) -> None:
        assert format_assistant_text("") == "●"

    def test_markdown_bold(self) -> None:
        result = format_assistant_text("**bold** text")
        assert result == "● **bold** text"

    def test_markdown_list(self) -> None:
        result = format_assistant_text("Here:\n- item 1\n- item 2")
        assert result == "● Here:\n  - item 1\n  - item 2"

    def test_markdown_code_block(self) -> None:
        result = format_assistant_text("Code:\n```python\nx = 1\n```")
        assert result == "● Code:\n  ```python\n  x = 1\n  ```"

    def test_special_characters(self) -> None:
        result = format_assistant_text("<tag> & \"quotes\" ñ 日本語")
        assert result == "● <tag> & \"quotes\" ñ 日本語"


class TestFormatElement:
    """Tests for format_element."""

    def test_user_message(self) -> None:
        elem = UserMessage(text="❯ hello")
        assert format_element(elem) == "❯ hello"

    def test_system_output(self) -> None:
        elem = SystemOutput(text="some output")
        assert format_element(elem) == "some output"

    def test_unknown_element(self) -> None:
        elem = ThinkingIndicator()
        assert format_element(elem) == ""

    def test_assistant_text(self) -> None:
        elem = AssistantText(text="● response")
        assert format_element(elem) == "● response"

    def test_assistant_text_with_request_id(self) -> None:
        elem = AssistantText(text="● response", request_id="req_001")
        assert format_element(elem) == "● response"

    def test_tool_call_basic(self) -> None:
        elem = ToolCall(tool_name="Bash", tool_use_id="t1", label="ls -la")
        assert format_element(elem) == "\u25cf Bash(ls -la)"

    def test_tool_call_with_request_id(self) -> None:
        elem = ToolCall(tool_name="Read", tool_use_id="t2", label="file.py", request_id="req_001")
        assert format_element(elem) == "\u25cf Read(file.py)"

    def test_tool_call_with_single_line_result(self) -> None:
        elem = ToolCall(tool_name="Bash", tool_use_id="t1", label="ls", result="file.py")
        result = format_element(elem)
        assert result == "\u25cf Bash(ls)\n  \u2514 file.py"

    def test_tool_call_with_multiline_result(self) -> None:
        elem = ToolCall(
            tool_name="Bash", tool_use_id="t1", label="git status",
            result="On branch main\nYour branch is up to date\nChanges not staged:\n  modified: file.py"
        )
        result = format_element(elem)
        expected = (
            "\u25cf Bash(git status)\n"
            "  \u2514 On branch main\n"
            "    Your branch is up to date\n"
            "    Changes not staged:\n"
            "      modified: file.py"
        )
        assert result == expected

    def test_tool_call_with_error_result(self) -> None:
        elem = ToolCall(
            tool_name="Bash", tool_use_id="t1", label="bad command",
            result="command not found: bad", is_error=True
        )
        result = format_element(elem)
        assert result == "\u25cf Bash(bad command)\n  \u2717 command not found: bad"

    def test_tool_call_with_multiline_error(self) -> None:
        elem = ToolCall(
            tool_name="Bash", tool_use_id="t1", label="failing script",
            result="error: failed\ndetails: something went wrong", is_error=True
        )
        result = format_element(elem)
        expected = (
            "\u25cf Bash(failing script)\n"
            "  \u2717 error: failed\n"
            "    details: something went wrong"
        )
        assert result == expected

    def test_tool_call_with_truncated_result(self) -> None:
        """Result is already truncated with … marker."""
        elem = ToolCall(
            tool_name="Bash", tool_use_id="t1", label="long output",
            result="line1\nline2\nline3\nline4\n…"
        )
        result = format_element(elem)
        expected = (
            "\u25cf Bash(long output)\n"
            "  \u2514 line1\n"
            "    line2\n"
            "    line3\n"
            "    line4\n"
            "    …"
        )
        assert result == expected


class TestToMarkdown:
    """Tests for to_markdown output."""

    def test_empty_state(self) -> None:
        state = ScreenState()
        assert to_markdown(state) == ""

    def test_single_user_message(self) -> None:
        state = ScreenState(elements=[UserMessage(text="❯ hello")])
        assert to_markdown(state) == "❯ hello"

    def test_two_user_messages(self) -> None:
        state = ScreenState(
            elements=[
                UserMessage(text="❯ first"),
                UserMessage(text="❯ second"),
            ]
        )
        assert to_markdown(state) == "❯ first\n\n❯ second"

    def test_user_plus_system_output(self) -> None:
        state = ScreenState(
            elements=[
                UserMessage(text="❯ hello"),
                SystemOutput(text="output here"),
            ]
        )
        result = to_markdown(state)
        assert result == "❯ hello\n\noutput here"

    def test_mixed_elements_in_order(self) -> None:
        state = ScreenState(
            elements=[
                UserMessage(text="❯ first"),
                SystemOutput(text="middle"),
                UserMessage(text="❯ last"),
            ]
        )
        result = to_markdown(state)
        assert result == "❯ first\n\nmiddle\n\n❯ last"

    def test_state_to_markdown_delegates(self) -> None:
        """Verify ScreenState.to_markdown() uses formatter."""
        state = ScreenState(elements=[UserMessage(text="❯ via method")])
        assert state.to_markdown() == "❯ via method"


class TestToMarkdownRequestIdGrouping:
    """Tests for request_id-based grouping in to_markdown."""

    def test_same_request_id_no_blank_line(self) -> None:
        """Two assistant texts with same requestId have no blank line."""
        state = ScreenState(
            elements=[
                AssistantText(text="● first", request_id="req_001"),
                AssistantText(text="● second", request_id="req_001"),
            ]
        )
        result = to_markdown(state)
        assert result == "● first\n● second"

    def test_different_request_ids_blank_line(self) -> None:
        """Two assistant texts with different requestIds have blank line."""
        state = ScreenState(
            elements=[
                AssistantText(text="● first", request_id="req_001"),
                AssistantText(text="● second", request_id="req_002"),
            ]
        )
        result = to_markdown(state)
        assert result == "● first\n\n● second"

    def test_user_then_assistant_blank_line(self) -> None:
        """User message then assistant text have blank line."""
        state = ScreenState(
            elements=[
                UserMessage(text="❯ hello"),
                AssistantText(text="● response", request_id="req_001"),
            ]
        )
        result = to_markdown(state)
        assert result == "❯ hello\n\n● response"

    def test_user_assistant_assistant_same_rid(self) -> None:
        """User → assistant(req_1) → assistant(req_1): blank before first, none between."""
        state = ScreenState(
            elements=[
                UserMessage(text="❯ hello"),
                AssistantText(text="● part 1", request_id="req_001"),
                AssistantText(text="● part 2", request_id="req_001"),
            ]
        )
        result = to_markdown(state)
        assert result == "❯ hello\n\n● part 1\n● part 2"

    def test_user_assistant_user_assistant(self) -> None:
        """User → assistant(req_1) → user → assistant(req_2): proper spacing."""
        state = ScreenState(
            elements=[
                UserMessage(text="❯ first"),
                AssistantText(text="● resp 1", request_id="req_001"),
                UserMessage(text="❯ second"),
                AssistantText(text="● resp 2", request_id="req_002"),
            ]
        )
        result = to_markdown(state)
        assert result == "❯ first\n\n● resp 1\n\n❯ second\n\n● resp 2"

    def test_three_blocks_same_request_id(self) -> None:
        """Three assistant blocks with same requestId: no blank lines between any."""
        state = ScreenState(
            elements=[
                AssistantText(text="● a", request_id="req_001"),
                AssistantText(text="● b", request_id="req_001"),
                AssistantText(text="● c", request_id="req_001"),
            ]
        )
        result = to_markdown(state)
        assert result == "● a\n● b\n● c"

    def test_none_request_id_treated_as_different(self) -> None:
        """Elements with None request_id always get blank line separator."""
        state = ScreenState(
            elements=[
                AssistantText(text="● first", request_id=None),
                AssistantText(text="● second", request_id=None),
            ]
        )
        result = to_markdown(state)
        assert result == "● first\n\n● second"

    def test_tool_call_grouped_by_request_id(self) -> None:
        """ToolCall elements with same requestId grouped without blank line."""
        state = ScreenState(
            elements=[
                ToolCall(tool_name="Bash", tool_use_id="t1", label="ls", request_id="req_001"),
                ToolCall(tool_name="Read", tool_use_id="t2", label="f.py", request_id="req_001"),
            ]
        )
        result = to_markdown(state)
        assert result == "\u25cf Bash(ls)\n\u25cf Read(f.py)"

    def test_text_and_tool_call_same_rid(self) -> None:
        """AssistantText + ToolCall with same requestId: no blank line."""
        state = ScreenState(
            elements=[
                AssistantText(text="\u25cf checking", request_id="req_001"),
                ToolCall(tool_name="Bash", tool_use_id="t1", label="ls", request_id="req_001"),
            ]
        )
        result = to_markdown(state)
        assert result == "\u25cf checking\n\u25cf Bash(ls)"
