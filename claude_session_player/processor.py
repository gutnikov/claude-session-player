"""Event processor: converts JSONL lines to events."""

from __future__ import annotations

import uuid

from .events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    DurationContent,
    Event,
    ProcessingContext,
    SystemContent,
    ThinkingContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from .formatter import truncate_result
from .parser import (
    LineType,
    classify_line,
    get_duration_ms,
    get_local_command_text,
    get_parent_tool_use_id,
    get_progress_data,
    get_request_id,
    get_tool_result_info,
    get_tool_use_info,
    get_user_text,
)
from .tools import abbreviate_tool_input


# Module-level cache for tool call content (cleared on compact_boundary)
# This stores the original ToolCallContent so we can create complete UpdateBlocks
_tool_content_cache: dict[str, ToolCallContent] = {}


def _store_tool_content(tool_use_id: str, content: ToolCallContent) -> None:
    """Store tool call content for later result/progress updates."""
    _tool_content_cache[tool_use_id] = content


def _clear_tool_content_cache() -> None:
    """Clear the tool content cache."""
    _tool_content_cache.clear()


def process_line(context: ProcessingContext, line: dict) -> list[Event]:
    """Process a single JSONL line and return events.

    Args:
        context: Processing context with state (tool mappings, request ID).
        line: Parsed JSONL line dict.

    Returns:
        List of events (AddBlock, UpdateBlock, or ClearAll).
    """
    line_type = classify_line(line)

    if line_type is LineType.INVISIBLE:
        return []
    if line_type is LineType.USER_INPUT:
        return _process_user_input(context, line)
    if line_type is LineType.LOCAL_COMMAND_OUTPUT:
        return _process_local_command(line)
    if line_type is LineType.ASSISTANT_TEXT:
        return _process_assistant_text(context, line)
    if line_type is LineType.TOOL_USE:
        return _process_tool_use(context, line)
    if line_type is LineType.TOOL_RESULT:
        return _process_tool_result(context, line)
    if line_type is LineType.THINKING:
        return _process_thinking(context, line)
    if line_type is LineType.TURN_DURATION:
        return _process_turn_duration(context, line)
    if line_type is LineType.COMPACT_BOUNDARY:
        return _process_compact_boundary(context)
    if line_type is LineType.BASH_PROGRESS:
        return _process_bash_progress(context, line)
    if line_type is LineType.HOOK_PROGRESS:
        return _process_hook_progress(context, line)
    if line_type is LineType.AGENT_PROGRESS:
        return _process_agent_progress(context, line)
    if line_type is LineType.QUERY_UPDATE:
        return _process_query_update(context, line)
    if line_type is LineType.SEARCH_RESULTS:
        return _process_search_results(context, line)
    if line_type is LineType.WAITING_FOR_TASK:
        return _process_waiting_for_task(context, line)

    # Unknown line type - return empty list
    return []


def _generate_block_id() -> str:
    """Generate a unique block ID using UUID."""
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# User message processors
# ---------------------------------------------------------------------------


def _process_user_input(context: ProcessingContext, line: dict) -> list[Event]:
    """Process USER_INPUT: create AddBlock(USER)."""
    text = get_user_text(line)
    content = UserContent(text=text)
    block = Block(
        id=_generate_block_id(),
        type=BlockType.USER,
        content=content,
    )
    # Reset current_request_id on user input
    context.current_request_id = None
    return [AddBlock(block=block)]


def _process_local_command(line: dict) -> list[Event]:
    """Process LOCAL_COMMAND_OUTPUT: create AddBlock(SYSTEM)."""
    text = get_local_command_text(line)
    content = SystemContent(text=text)
    block = Block(
        id=_generate_block_id(),
        type=BlockType.SYSTEM,
        content=content,
    )
    return [AddBlock(block=block)]


# ---------------------------------------------------------------------------
# Assistant message processors
# ---------------------------------------------------------------------------


def _process_assistant_text(context: ProcessingContext, line: dict) -> list[Event]:
    """Process ASSISTANT_TEXT: create AddBlock(ASSISTANT)."""
    request_id = get_request_id(line)
    message = line.get("message") or {}
    content_list = message.get("content") or []

    text = ""
    if content_list and isinstance(content_list, list):
        first_block = content_list[0]
        if isinstance(first_block, dict):
            text = first_block.get("text", "")

    content = AssistantContent(text=text)
    block = Block(
        id=_generate_block_id(),
        type=BlockType.ASSISTANT,
        content=content,
        request_id=request_id,
    )
    context.current_request_id = request_id
    return [AddBlock(block=block)]


def _process_tool_use(context: ProcessingContext, line: dict) -> list[Event]:
    """Process TOOL_USE: create AddBlock(TOOL_CALL), store mapping."""
    tool_name, tool_use_id, input_dict = get_tool_use_info(line)
    label = abbreviate_tool_input(tool_name, input_dict)
    request_id = get_request_id(line)

    content = ToolCallContent(
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        label=label,
    )
    block_id = _generate_block_id()
    block = Block(
        id=block_id,
        type=BlockType.TOOL_CALL,
        content=content,
        request_id=request_id,
    )

    # Store mapping for later result/progress updates
    context.tool_use_id_to_block_id[tool_use_id] = block_id
    # Store content for later updates
    _store_tool_content(tool_use_id, content)
    context.current_request_id = request_id
    return [AddBlock(block=block)]


def _process_thinking(context: ProcessingContext, line: dict) -> list[Event]:
    """Process THINKING: create AddBlock(THINKING)."""
    request_id = get_request_id(line)
    content = ThinkingContent()
    block = Block(
        id=_generate_block_id(),
        type=BlockType.THINKING,
        content=content,
        request_id=request_id,
    )
    context.current_request_id = request_id
    return [AddBlock(block=block)]


# ---------------------------------------------------------------------------
# System message processors
# ---------------------------------------------------------------------------


def _process_turn_duration(context: ProcessingContext, line: dict) -> list[Event]:
    """Process TURN_DURATION: create AddBlock(DURATION)."""
    duration_ms = get_duration_ms(line)
    content = DurationContent(duration_ms=duration_ms)
    block = Block(
        id=_generate_block_id(),
        type=BlockType.DURATION,
        content=content,
    )
    # Reset current_request_id on turn duration
    context.current_request_id = None
    return [AddBlock(block=block)]


def _process_compact_boundary(context: ProcessingContext) -> list[Event]:
    """Process COMPACT_BOUNDARY: return ClearAll, clear context."""
    context.clear()
    _clear_tool_content_cache()
    return [ClearAll()]


# ---------------------------------------------------------------------------
# Tool result processor
# ---------------------------------------------------------------------------


def _get_task_result_text(line: dict) -> str | None:
    """Extract collapsed result text for Task tool results.

    Task tool results have a special structure with toolUseResult containing
    status, agentId, content, totalDurationMs, etc. Extract and truncate
    the first 80 chars of the content text.

    Returns None if this isn't a Task result or content isn't available.
    """
    tur = line.get("toolUseResult", {})
    if isinstance(tur, dict) and "content" in tur:
        content_list = tur.get("content", [])
        if content_list and isinstance(content_list, list) and len(content_list) > 0:
            first_block = content_list[0]
            if isinstance(first_block, dict):
                text = first_block.get("text", "")
                if text:
                    if len(text) > 80:
                        return text[:79] + "…"
                    return text
    return None


def _process_tool_result(context: ProcessingContext, line: dict) -> list[Event]:
    """Process TOOL_RESULT: UpdateBlock if match found, else AddBlock(SYSTEM)."""
    results = get_tool_result_info(line)
    events: list[Event] = []

    # Check for Task tool result special handling
    task_result_text = _get_task_result_text(line)

    for tool_use_id, content_text, is_error in results:
        if tool_use_id in context.tool_use_id_to_block_id:
            # Found matching tool call - create UpdateBlock
            block_id = context.tool_use_id_to_block_id[tool_use_id]
            result_text = truncate_result(content_text)

            # Get original content from cache to create complete UpdateBlock
            original = _tool_content_cache.get(tool_use_id)
            if original:
                # Check if this is a Task tool with special result handling
                if original.tool_name == "Task" and task_result_text is not None:
                    result_text = task_result_text

                updated_content = ToolCallContent(
                    tool_name=original.tool_name,
                    tool_use_id=original.tool_use_id,
                    label=original.label,
                    result=result_text,
                    is_error=is_error,
                    progress_text=original.progress_text,
                )
                # Update cache so subsequent progress messages preserve the result
                _store_tool_content(tool_use_id, updated_content)
            else:
                # Fallback: create content with empty tool_name/label
                # This shouldn't happen in normal operation
                updated_content = ToolCallContent(
                    tool_name="",
                    tool_use_id=tool_use_id,
                    label="",
                    result=result_text,
                    is_error=is_error,
                )

            events.append(UpdateBlock(block_id=block_id, content=updated_content))
        else:
            # Orphan result - create AddBlock(SYSTEM)
            truncated = truncate_result(content_text)
            content = SystemContent(text=truncated)
            block = Block(
                id=_generate_block_id(),
                type=BlockType.SYSTEM,
                content=content,
            )
            events.append(AddBlock(block=block))

    return events


# ---------------------------------------------------------------------------
# Progress message processors
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


def _update_tool_progress(
    context: ProcessingContext, parent_id: str | None, progress_text: str
) -> list[Event]:
    """Create UpdateBlock for tool call progress if match found."""
    if not parent_id or parent_id not in context.tool_use_id_to_block_id:
        return []

    block_id = context.tool_use_id_to_block_id[parent_id]
    original = _tool_content_cache.get(parent_id)

    if original:
        updated_content = ToolCallContent(
            tool_name=original.tool_name,
            tool_use_id=original.tool_use_id,
            label=original.label,
            result=original.result,
            is_error=original.is_error,
            progress_text=progress_text,
        )
        # Update cache with new progress
        _store_tool_content(parent_id, updated_content)
    else:
        # Fallback: shouldn't happen in normal operation
        updated_content = ToolCallContent(
            tool_name="",
            tool_use_id=parent_id,
            label="",
            progress_text=progress_text,
        )

    return [UpdateBlock(block_id=block_id, content=updated_content)]


def _process_bash_progress(context: ProcessingContext, line: dict) -> list[Event]:
    """Process BASH_PROGRESS: UpdateBlock with last line of fullOutput."""
    data = get_progress_data(line)
    parent_id = get_parent_tool_use_id(line)
    progress_text = _get_bash_progress_text(data)
    return _update_tool_progress(context, parent_id, progress_text)


def _process_hook_progress(context: ProcessingContext, line: dict) -> list[Event]:
    """Process HOOK_PROGRESS: UpdateBlock with Hook: {hookName}."""
    data = get_progress_data(line)
    parent_id = get_parent_tool_use_id(line)
    hook_name = data.get("hookName", "")
    progress_text = f"Hook: {hook_name}"
    return _update_tool_progress(context, parent_id, progress_text)


def _process_agent_progress(context: ProcessingContext, line: dict) -> list[Event]:
    """Process AGENT_PROGRESS: UpdateBlock with fixed 'Agent: working…'."""
    parent_id = get_parent_tool_use_id(line)
    progress_text = "Agent: working…"
    return _update_tool_progress(context, parent_id, progress_text)


def _process_query_update(context: ProcessingContext, line: dict) -> list[Event]:
    """Process QUERY_UPDATE: UpdateBlock with Searching: {query}."""
    data = get_progress_data(line)
    parent_id = get_parent_tool_use_id(line)
    query = data.get("query", "")
    progress_text = f"Searching: {query}"
    return _update_tool_progress(context, parent_id, progress_text)


def _process_search_results(context: ProcessingContext, line: dict) -> list[Event]:
    """Process SEARCH_RESULTS: UpdateBlock with {resultCount} results."""
    data = get_progress_data(line)
    parent_id = get_parent_tool_use_id(line)
    result_count = data.get("resultCount", 0)
    progress_text = f"{result_count} results"
    return _update_tool_progress(context, parent_id, progress_text)


def _process_waiting_for_task(context: ProcessingContext, line: dict) -> list[Event]:
    """Process WAITING_FOR_TASK: UpdateBlock if match, else AddBlock(SYSTEM)."""
    data = get_progress_data(line)
    parent_id = get_parent_tool_use_id(line)
    description = data.get("taskDescription", "")
    progress_text = f"Waiting: {description}"

    if parent_id and parent_id in context.tool_use_id_to_block_id:
        return _update_tool_progress(context, parent_id, progress_text)
    else:
        # No matching tool call - create standalone SystemOutput
        content = SystemContent(text=f"└ {progress_text}")
        block = Block(
            id=_generate_block_id(),
            type=BlockType.SYSTEM,
            content=content,
        )
        return [AddBlock(block=block)]
