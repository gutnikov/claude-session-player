"""Render function: processes JSONL lines into screen state."""

from __future__ import annotations

from .formatter import format_assistant_text, format_user_text, truncate_result
from .models import AssistantText, ScreenState, SystemOutput, ToolCall, UserMessage
from .parser import LineType, classify_line, get_local_command_text, get_request_id, get_tool_result_info, get_tool_use_info, get_user_text
from .tools import abbreviate_tool_input


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
    elif line_type is LineType.TOOL_USE:
        _render_tool_use(state, line)
    elif line_type is LineType.TOOL_RESULT:
        _render_tool_result(state, line)
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


def _render_tool_use(state: ScreenState, line: dict) -> None:
    """Render a tool_use assistant block."""
    tool_name, tool_use_id, input_dict = get_tool_use_info(line)
    label = abbreviate_tool_input(tool_name, input_dict)
    request_id = get_request_id(line)

    tool_call = ToolCall(
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        label=label,
        request_id=request_id,
    )
    state.elements.append(tool_call)
    state.tool_calls[tool_use_id] = len(state.elements) - 1
    state.current_request_id = request_id


def _render_tool_result(state: ScreenState, line: dict) -> None:
    """Render tool result(s) by matching to existing tool calls.

    For each tool result:
    - If tool_use_id matches a tool call in state.tool_calls, update that ToolCall
      element with the truncated result and is_error flag.
    - If no match found (orphan result), append a SystemOutput with the content.

    Tool results break assistant grouping, so current_request_id is reset to None.
    """
    results = get_tool_result_info(line)

    for tool_use_id, content, is_error in results:
        if tool_use_id in state.tool_calls:
            # Found matching tool call - update it
            index = state.tool_calls[tool_use_id]
            element = state.elements[index]
            if isinstance(element, ToolCall):
                element.result = truncate_result(content)
                element.is_error = is_error
        else:
            # Orphan result - render as system output
            truncated = truncate_result(content)
            state.elements.append(SystemOutput(text=truncated))

    # Tool result breaks assistant grouping
    state.current_request_id = None
