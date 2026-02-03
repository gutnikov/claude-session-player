"""Render function: processes JSONL lines into screen state."""

from __future__ import annotations

from .formatter import format_assistant_text, format_user_text, truncate_result
from .models import AssistantText, ScreenState, SystemOutput, ThinkingIndicator, ToolCall, TurnDuration, UserMessage
from .parser import LineType, classify_line, get_duration_ms, get_local_command_text, get_parent_tool_use_id, get_progress_data, get_request_id, get_tool_result_info, get_tool_use_info, get_user_text
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
    elif line_type is LineType.THINKING:
        _render_thinking(state, line)
    elif line_type is LineType.TURN_DURATION:
        _render_turn_duration(state, line)
    elif line_type is LineType.COMPACT_BOUNDARY:
        _render_compact_boundary(state)
    elif line_type is LineType.BASH_PROGRESS:
        _render_bash_progress(state, line)
    elif line_type is LineType.HOOK_PROGRESS:
        _render_hook_progress(state, line)
    elif line_type is LineType.AGENT_PROGRESS:
        _render_agent_progress(state, line)
    elif line_type is LineType.QUERY_UPDATE:
        _render_query_update(state, line)
    elif line_type is LineType.SEARCH_RESULTS:
        _render_search_results(state, line)
    elif line_type is LineType.WAITING_FOR_TASK:
        _render_waiting_for_task(state, line)
    # INVISIBLE and unhandled types: do nothing

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


def _render_thinking(state: ScreenState, line: dict) -> None:
    """Render a thinking indicator."""
    request_id = get_request_id(line)
    state.elements.append(ThinkingIndicator(request_id=request_id))
    state.current_request_id = request_id


def _render_turn_duration(state: ScreenState, line: dict) -> None:
    """Render turn duration timing line."""
    duration_ms = get_duration_ms(line)
    state.elements.append(TurnDuration(duration_ms=duration_ms))
    state.current_request_id = None


def _render_compact_boundary(state: ScreenState) -> None:
    """Handle compact boundary by clearing all state."""
    state.clear()


# ---------------------------------------------------------------------------
# Progress message handlers
# ---------------------------------------------------------------------------


def _get_bash_progress_text(data: dict) -> str:
    """Extract the last non-empty line from bash progress fullOutput.

    Truncates to 76 chars to fit within 80 cols with the `  └ ` prefix.
    """
    full_output = data.get("fullOutput", "")
    lines = [line for line in full_output.split("\n") if line.strip()]
    if not lines:
        return "running…"
    last_line = lines[-1]
    if len(last_line) > 76:
        return last_line[:75] + "…"
    return last_line


def _update_tool_call_progress(state: ScreenState, parent_id: str | None, progress_text: str) -> bool:
    """Update progress_text on matching tool call.

    Returns True if a match was found, False otherwise.
    """
    if parent_id and parent_id in state.tool_calls:
        index = state.tool_calls[parent_id]
        element = state.elements[index]
        if isinstance(element, ToolCall):
            element.progress_text = progress_text
            return True
    return False


def _render_bash_progress(state: ScreenState, line: dict) -> None:
    """Render bash_progress: update ToolCall with last line of fullOutput."""
    data = get_progress_data(line)
    parent_id = get_parent_tool_use_id(line)
    progress_text = _get_bash_progress_text(data)
    _update_tool_call_progress(state, parent_id, progress_text)


def _render_hook_progress(state: ScreenState, line: dict) -> None:
    """Render hook_progress: update ToolCall with Hook: {hookName}."""
    data = get_progress_data(line)
    parent_id = get_parent_tool_use_id(line)
    hook_name = data.get("hookName", "")
    progress_text = f"Hook: {hook_name}"
    _update_tool_call_progress(state, parent_id, progress_text)


def _render_agent_progress(state: ScreenState, line: dict) -> None:
    """Render agent_progress: update ToolCall with fixed 'Agent: working…'."""
    parent_id = get_parent_tool_use_id(line)
    progress_text = "Agent: working…"
    _update_tool_call_progress(state, parent_id, progress_text)


def _render_query_update(state: ScreenState, line: dict) -> None:
    """Render query_update: update ToolCall with Searching: {query}."""
    data = get_progress_data(line)
    parent_id = get_parent_tool_use_id(line)
    query = data.get("query", "")
    progress_text = f"Searching: {query}"
    _update_tool_call_progress(state, parent_id, progress_text)


def _render_search_results(state: ScreenState, line: dict) -> None:
    """Render search_results_received: update ToolCall with {resultCount} results."""
    data = get_progress_data(line)
    parent_id = get_parent_tool_use_id(line)
    result_count = data.get("resultCount", 0)
    progress_text = f"{result_count} results"
    _update_tool_call_progress(state, parent_id, progress_text)


def _render_waiting_for_task(state: ScreenState, line: dict) -> None:
    """Render waiting_for_task: update ToolCall or create standalone SystemOutput.

    If parentToolUseID matches a tool call, update that tool call's progress.
    Otherwise, create a standalone SystemOutput element.
    """
    data = get_progress_data(line)
    parent_id = get_parent_tool_use_id(line)
    description = data.get("taskDescription", "")
    progress_text = f"Waiting: {description}"

    matched = _update_tool_call_progress(state, parent_id, progress_text)
    if not matched:
        # No matching tool call - render as standalone SystemOutput
        state.elements.append(SystemOutput(text=f"└ {progress_text}"))
