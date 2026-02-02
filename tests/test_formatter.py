"""Tests for markdown formatting."""

from __future__ import annotations

from claude_session_player.models import ScreenElement
from claude_session_player.formatter import format_element, format_elements


class TestFormatUserMessage:
    def test_single_line(self) -> None:
        el = ScreenElement(kind="user_message", text="hello world")
        assert format_element(el) == "\u276f hello world"

    def test_multiline(self) -> None:
        el = ScreenElement(kind="user_message", text="line one\nline two\nline three")
        result = format_element(el)
        lines = result.split("\n")
        assert lines[0] == "\u276f line one"
        assert lines[1] == "  line two"
        assert lines[2] == "  line three"

    def test_empty_text(self) -> None:
        el = ScreenElement(kind="user_message", text="")
        assert format_element(el) == "\u276f"


class TestFormatAssistantText:
    def test_single_line(self) -> None:
        el = ScreenElement(kind="assistant_text", text="I will help you.")
        assert format_element(el) == "\u25cf I will help you."

    def test_multiline(self) -> None:
        el = ScreenElement(kind="assistant_text", text="First line\nSecond line")
        result = format_element(el)
        lines = result.split("\n")
        assert lines[0] == "\u25cf First line"
        assert lines[1] == "  Second line"

    def test_empty_text(self) -> None:
        el = ScreenElement(kind="assistant_text", text="")
        assert format_element(el) == "\u25cf"


class TestFormatToolCall:
    def test_no_result(self) -> None:
        el = ScreenElement(kind="tool_call", tool_name="Read", label="README.md")
        assert format_element(el) == "\u25cf Read(README.md)"

    def test_with_result(self) -> None:
        el = ScreenElement(kind="tool_call", tool_name="Read", label="README.md", result="file contents")
        result = format_element(el)
        lines = result.split("\n")
        assert lines[0] == "\u25cf Read(README.md)"
        assert lines[1] == "  \u2514 file contents"

    def test_with_error(self) -> None:
        el = ScreenElement(
            kind="tool_call", tool_name="Read", label="missing.txt",
            result="File not found", is_error=True,
        )
        result = format_element(el)
        lines = result.split("\n")
        assert lines[0] == "\u25cf Read(missing.txt)"
        assert lines[1] == "  \u2717 File not found"

    def test_result_truncation(self) -> None:
        """Results longer than 5 lines should be truncated."""
        long_result = "\n".join(f"line {i}" for i in range(10))
        el = ScreenElement(kind="tool_call", tool_name="Bash", label="ls", result=long_result)
        result = format_element(el)
        lines = result.split("\n")
        # header + 4 result lines + truncation indicator = 6
        assert lines[-1] == "  \u2514 \u2026"
        # Should have header (1) + 4 content lines + truncation = 6 lines total
        assert len(lines) == 6

    def test_result_exactly_5_lines(self) -> None:
        """5 line result should not be truncated."""
        five_lines = "\n".join(f"line {i}" for i in range(5))
        el = ScreenElement(kind="tool_call", tool_name="Bash", label="ls", result=five_lines)
        result = format_element(el)
        lines = result.split("\n")
        # header + 5 result lines = 6 (no truncation indicator)
        assert "\u2514 \u2026" not in lines[-1]

    def test_multiline_result(self) -> None:
        """Multi-line results should have indented continuation."""
        el = ScreenElement(
            kind="tool_call", tool_name="Bash", label="ls",
            result="file1.txt\nfile2.txt\nfile3.txt",
        )
        result = format_element(el)
        lines = result.split("\n")
        assert lines[0] == "\u25cf Bash(ls)"
        assert lines[1] == "  \u2514 file1.txt"
        assert lines[2] == "    file2.txt"
        assert lines[3] == "    file3.txt"


class TestFormatThinking:
    def test_thinking(self) -> None:
        el = ScreenElement(kind="thinking")
        assert format_element(el) == "\u2731 Thinking\u2026"


class TestFormatTurnDuration:
    def test_short_duration(self) -> None:
        el = ScreenElement(kind="turn_duration", duration_ms=5500)
        assert format_element(el) == "\u2731 Crunched for 5s"

    def test_long_duration(self) -> None:
        el = ScreenElement(kind="turn_duration", duration_ms=88947)
        assert format_element(el) == "\u2731 Crunched for 1m 28s"

    def test_exactly_60s(self) -> None:
        el = ScreenElement(kind="turn_duration", duration_ms=60000)
        assert format_element(el) == "\u2731 Crunched for 1m 0s"

    def test_zero_duration(self) -> None:
        el = ScreenElement(kind="turn_duration", duration_ms=0)
        assert format_element(el) == "\u2731 Crunched for 0s"


class TestFormatSystemOutput:
    def test_system_output(self) -> None:
        el = ScreenElement(kind="system_output", text="git status output")
        assert format_element(el) == "git status output"


class TestFormatElements:
    """Test element grouping and blank line insertion."""

    def test_empty_elements(self) -> None:
        assert format_elements([], None) == ""

    def test_single_element(self) -> None:
        elements = [ScreenElement(kind="user_message", text="hello")]
        result = format_elements(elements, None)
        assert result == "\u276f hello"

    def test_blank_line_between_different_groups(self) -> None:
        elements = [
            ScreenElement(kind="user_message", text="hello"),
            ScreenElement(kind="assistant_text", text="hi", request_id="req_1"),
        ]
        result = format_elements(elements, None)
        lines = result.split("\n")
        assert lines[0] == "\u276f hello"
        assert lines[1] == ""  # blank line
        assert lines[2] == "\u25cf hi"

    def test_no_blank_line_within_same_request(self) -> None:
        elements = [
            ScreenElement(kind="thinking", request_id="req_1"),
            ScreenElement(kind="assistant_text", text="response", request_id="req_1"),
        ]
        result = format_elements(elements, None)
        lines = result.split("\n")
        assert lines[0] == "\u2731 Thinking\u2026"
        assert lines[1] == "\u25cf response"
        # No blank line between them

    def test_blank_line_between_different_requests(self) -> None:
        elements = [
            ScreenElement(kind="assistant_text", text="first", request_id="req_1"),
            ScreenElement(kind="assistant_text", text="second", request_id="req_2"),
        ]
        result = format_elements(elements, None)
        lines = result.split("\n")
        assert lines[0] == "\u25cf first"
        assert lines[1] == ""  # blank line
        assert lines[2] == "\u25cf second"

    def test_full_session_formatting(self) -> None:
        """Test a realistic sequence of elements."""
        elements = [
            ScreenElement(kind="user_message", text="read the readme"),
            ScreenElement(kind="tool_call", tool_name="Read", label="README.md", request_id="req_1"),
            ScreenElement(kind="assistant_text", text="This project does X.", request_id="req_2"),
            ScreenElement(kind="turn_duration", duration_ms=3000),
        ]
        # Set a result on the tool call
        elements[1].result = "# My Project"

        result = format_elements(elements, None)
        lines = result.split("\n")

        # User message
        assert lines[0] == "\u276f read the readme"
        # Blank line
        assert lines[1] == ""
        # Tool call + result
        assert lines[2] == "\u25cf Read(README.md)"
        assert lines[3] == "  \u2514 # My Project"
        # Blank line
        assert lines[4] == ""
        # Assistant text
        assert lines[5] == "\u25cf This project does X."
        # Blank line
        assert lines[6] == ""
        # Duration
        assert lines[7] == "\u2731 Crunched for 3s"
