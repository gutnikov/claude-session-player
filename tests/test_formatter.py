"""Tests for formatting helpers."""

from __future__ import annotations

from claude_session_player.formatter import (
    format_duration,
    truncate_result,
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


class TestFormatDuration:
    """Tests for format_duration."""

    def test_zero_ms(self) -> None:
        assert format_duration(0) == "0s"

    def test_five_seconds(self) -> None:
        assert format_duration(5000) == "5s"

    def test_fifty_nine_seconds(self) -> None:
        assert format_duration(59999) == "59s"

    def test_sixty_seconds(self) -> None:
        assert format_duration(60000) == "1m 0s"

    def test_one_minute_five_seconds(self) -> None:
        assert format_duration(65000) == "1m 5s"

    def test_two_minutes_zero_seconds(self) -> None:
        assert format_duration(120000) == "2m 0s"

    def test_real_example_88947ms(self) -> None:
        """88947ms = 88.947s → 1m 28s."""
        assert format_duration(88947) == "1m 28s"
