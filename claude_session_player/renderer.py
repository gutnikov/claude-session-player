"""Render function: processes JSONL lines into screen state."""

from __future__ import annotations

from .formatter import format_assistant_text, format_user_text
from .models import AssistantText, ScreenState, SystemOutput, UserMessage
from .parser import LineType, classify_line, get_local_command_text, get_request_id, get_user_text


def render(state: ScreenState, line: dict) -> ScreenState:
    """Process a single JSONL line and update screen state.

    Args:
        state: Current screen state (mutated in place).
        line: Parsed JSONL line dict.

    Returns:
        The same state object, updated.
    """
    line_type = classify_line(line)

    if line_type is LineType.USER_INPUT:
        _render_user_input(state, line)
    elif line_type is LineType.LOCAL_COMMAND_OUTPUT:
        _render_local_command(state, line)
    elif line_type is LineType.ASSISTANT_TEXT:
        _render_assistant_text(state, line)
    # INVISIBLE and unhandled types: do nothing (future issues add more cases)

    return state


def _render_user_input(state: ScreenState, line: dict) -> None:
    """Render a user input message."""
    text = get_user_text(line)
    formatted = format_user_text(text)
    state.elements.append(UserMessage(text=formatted))
    state.current_request_id = None


def _render_local_command(state: ScreenState, line: dict) -> None:
    """Render local command output."""
    text = get_local_command_text(line)
    state.elements.append(SystemOutput(text=text))


def _render_assistant_text(state: ScreenState, line: dict) -> None:
    """Render an assistant text block."""
    request_id = get_request_id(line)
    message = line.get("message") or {}
    content = message.get("content") or []
    text = ""
    if content and isinstance(content, list):
        first_block = content[0]
        if isinstance(first_block, dict):
            text = first_block.get("text", "")

    formatted = format_assistant_text(text)
    state.elements.append(AssistantText(text=formatted, request_id=request_id))
    state.current_request_id = request_id
