"""Tests for formatting helpers and to_markdown output."""

from __future__ import annotations

from claude_session_player.formatter import format_element, format_user_text, to_markdown
from claude_session_player.models import (
    AssistantText,
    ScreenState,
    SystemOutput,
    ThinkingIndicator,
    UserMessage,
)


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

    def test_assistant_text_empty_for_now(self) -> None:
        elem = AssistantText(text="response")
        assert format_element(elem) == ""


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
