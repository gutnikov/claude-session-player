"""Tests for core data models."""

import pytest

from claude_session_player.models import (
    AssistantText,
    ScreenState,
    SystemOutput,
    ThinkingIndicator,
    ToolCall,
    TurnDuration,
    UserMessage,
)


class TestScreenStateInit:
    """Tests for ScreenState initialization."""

    def test_empty_elements(self, empty_state: ScreenState) -> None:
        assert empty_state.elements == []

    def test_empty_tool_calls(self, empty_state: ScreenState) -> None:
        assert empty_state.tool_calls == {}

    def test_none_request_id(self, empty_state: ScreenState) -> None:
        assert empty_state.current_request_id is None


class TestScreenStateClear:
    """Tests for ScreenState.clear()."""

    def test_clear_resets_elements(self) -> None:
        state = ScreenState(elements=[UserMessage(text="hello")])
        state.clear()
        assert state.elements == []

    def test_clear_resets_tool_calls(self) -> None:
        state = ScreenState(tool_calls={"id-1": 0})
        state.clear()
        assert state.tool_calls == {}

    def test_clear_resets_request_id(self) -> None:
        state = ScreenState(current_request_id="req-1")
        state.clear()
        assert state.current_request_id is None


class TestScreenElementVariants:
    """Tests for all ScreenElement variant dataclasses."""

    def test_user_message(self) -> None:
        msg = UserMessage(text="hello world")
        assert msg.text == "hello world"

    def test_assistant_text(self) -> None:
        txt = AssistantText(text="response here")
        assert txt.text == "response here"

    def test_tool_call_required_fields(self) -> None:
        tc = ToolCall(tool_name="Bash", tool_use_id="id-1", label="run tests")
        assert tc.tool_name == "Bash"
        assert tc.tool_use_id == "id-1"
        assert tc.label == "run tests"

    def test_tool_call_defaults(self) -> None:
        tc = ToolCall(tool_name="Read", tool_use_id="id-2", label="file.py")
        assert tc.result is None
        assert tc.is_error is False
        assert tc.progress_text is None

    def test_tool_call_with_result(self) -> None:
        tc = ToolCall(
            tool_name="Bash",
            tool_use_id="id-3",
            label="ls",
            result="file1\nfile2",
            is_error=False,
        )
        assert tc.result == "file1\nfile2"

    def test_tool_call_error(self) -> None:
        tc = ToolCall(
            tool_name="Bash",
            tool_use_id="id-4",
            label="fail",
            result="command not found",
            is_error=True,
        )
        assert tc.is_error is True

    def test_thinking_indicator(self) -> None:
        ti = ThinkingIndicator()
        assert isinstance(ti, ThinkingIndicator)

    def test_turn_duration(self) -> None:
        td = TurnDuration(duration_ms=5000)
        assert td.duration_ms == 5000

    def test_system_output(self) -> None:
        so = SystemOutput(text="some output")
        assert so.text == "some output"


class TestToolCallsMapping:
    """Tests for tool_calls dict mapping."""

    def test_maps_string_ids_to_int_indices(self) -> None:
        state = ScreenState()
        tc = ToolCall(tool_name="Bash", tool_use_id="abc-123", label="test")
        state.elements.append(tc)
        state.tool_calls["abc-123"] = 0
        assert state.tool_calls["abc-123"] == 0
        assert isinstance(state.elements[state.tool_calls["abc-123"]], ToolCall)


class TestElementsOrdering:
    """Tests for elements list ordering."""

    def test_maintains_insertion_order(self) -> None:
        state = ScreenState()
        state.elements.append(UserMessage(text="first"))
        state.elements.append(AssistantText(text="second"))
        state.elements.append(ToolCall(tool_name="Bash", tool_use_id="id-1", label="third"))
        assert isinstance(state.elements[0], UserMessage)
        assert isinstance(state.elements[1], AssistantText)
        assert isinstance(state.elements[2], ToolCall)


class TestTypeNarrowing:
    """Tests for isinstance type narrowing on ScreenElement."""

    def test_isinstance_checks(self) -> None:
        elements = [
            UserMessage(text="hi"),
            AssistantText(text="hello"),
            ToolCall(tool_name="Bash", tool_use_id="id-1", label="cmd"),
            ThinkingIndicator(),
            TurnDuration(duration_ms=1000),
            SystemOutput(text="output"),
        ]
        assert isinstance(elements[0], UserMessage)
        assert isinstance(elements[1], AssistantText)
        assert isinstance(elements[2], ToolCall)
        assert isinstance(elements[3], ThinkingIndicator)
        assert isinstance(elements[4], TurnDuration)
        assert isinstance(elements[5], SystemOutput)

    def test_not_isinstance_cross_types(self) -> None:
        msg = UserMessage(text="hi")
        assert not isinstance(msg, AssistantText)
        assert not isinstance(msg, ToolCall)


class TestToMarkdownNotImplemented:
    """Test that to_markdown raises NotImplementedError."""

    def test_to_markdown_raises(self, empty_state: ScreenState) -> None:
        with pytest.raises(NotImplementedError):
            empty_state.to_markdown()
