"""Core render function that dispatches JSONL lines to update screen state."""

from __future__ import annotations

import re

from claude_session_player.models import ScreenElement, ScreenState
from claude_session_player.tools import abbreviate_tool_input


def render(state: ScreenState, line: dict, *, allow_sidechain: bool = False) -> ScreenState:
    """Process a single JSONL line and update the screen state.

    Dispatches based on line["type"] and relevant subtypes. Returns the
    same (mutated) ScreenState instance.

    Args:
        allow_sidechain: If True, don't filter out isSidechain messages.
            Use this when replaying standalone subagent files.
    """
    line_type = line.get("type", "")

    # Filter out sidechain messages (sub-agent internals in main session files)
    if not allow_sidechain and line.get("isSidechain", False):
        return state

    if line_type == "user":
        _handle_user(state, line)
    elif line_type == "assistant":
        _handle_assistant(state, line)
    elif line_type == "system":
        _handle_system(state, line)
    elif line_type == "progress":
        _handle_progress(state, line)
    # summary, file-history-snapshot, queue-operation, pr-link are invisible

    return state


def _handle_user(state: ScreenState, line: dict) -> None:
    """Handle user-type messages."""
    # isMeta messages are invisible (skill expansions, caveats)
    if line.get("isMeta", False):
        return

    message = line.get("message", {})
    content = message.get("content", "")

    # String content
    if isinstance(content, str):
        # Check for local command stdout
        m = re.search(
            r"<local-command-stdout>(.*?)</local-command-stdout>",
            content,
            re.DOTALL,
        )
        if m:
            stdout_text = m.group(1).strip()
            state.elements.append(ScreenElement(kind="system_output", text=stdout_text))
            return

        # Direct user input
        state.elements.append(ScreenElement(kind="user_message", text=content))
        state.current_request_id = None
        return

    # List content
    if isinstance(content, list):
        # Check for tool_result blocks
        tool_results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
        if tool_results:
            _handle_tool_results(state, line, tool_results)
            return

        # Otherwise, direct user input from content blocks
        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)
        if text_parts:
            state.elements.append(ScreenElement(kind="user_message", text="\n".join(text_parts)))
            state.current_request_id = None


def _handle_tool_results(
    state: ScreenState,
    line: dict,
    tool_results: list[dict],
) -> None:
    """Handle tool result blocks from a user message."""
    tool_use_result = line.get("toolUseResult", {})
    if not isinstance(tool_use_result, dict):
        tool_use_result = {}

    for block in tool_results:
        tool_use_id = block.get("tool_use_id", "")
        is_error = block.get("is_error", False)

        # Extract result text
        result_text = _extract_tool_result_text(block, tool_use_result, state, tool_use_id)

        # Find the matching tool call element
        if tool_use_id in state.tool_calls:
            idx = state.tool_calls[tool_use_id]
            el = state.elements[idx]
            el.result = result_text
            el.is_error = is_error
            el.result_is_final = True


def _extract_tool_result_text(
    block: dict,
    tool_use_result: dict,
    state: ScreenState,
    tool_use_id: str,
) -> str:
    """Extract display text from a tool result block."""
    # Determine the tool name from the matching tool call
    tool_name = ""
    if tool_use_id in state.tool_calls:
        idx = state.tool_calls[tool_use_id]
        tool_name = state.elements[idx].tool_name

    # For Task tool, use toolUseResult.content[0].text (first 80 chars)
    if tool_name == "Task" and tool_use_result:
        tur_content = tool_use_result.get("content", [])
        if isinstance(tur_content, list) and tur_content:
            first_block = tur_content[0]
            if isinstance(first_block, dict):
                text = first_block.get("text", "")
                if len(text) > 80:
                    return text[:79] + "\u2026"
                return text

    # For Bash tool, prefer toolUseResult.stdout
    if tool_name == "Bash" and tool_use_result:
        stdout = tool_use_result.get("stdout")
        if stdout is not None:
            return stdout

    # Fall back to block content
    block_content = block.get("content", "")

    if isinstance(block_content, str):
        return block_content

    if isinstance(block_content, list):
        for sub_block in block_content:
            if isinstance(sub_block, dict) and sub_block.get("type") == "text":
                return sub_block.get("text", "")

    return ""


def _handle_assistant(state: ScreenState, line: dict) -> None:
    """Handle assistant-type messages."""
    message = line.get("message", {})
    content_blocks = message.get("content", [])
    request_id = line.get("requestId", "")

    state.current_request_id = request_id

    for block in content_blocks:
        if not isinstance(block, dict):
            continue

        block_type = block.get("type", "")

        if block_type == "text":
            text = block.get("text", "")
            # Filter out placeholder "(no content)" text blocks
            if not text or text == "(no content)":
                continue
            state.elements.append(
                ScreenElement(kind="assistant_text", text=text, request_id=request_id)
            )
        elif block_type == "tool_use":
            tool_name = block.get("name", "")
            tool_input = block.get("input", {})
            tool_id = block.get("id", "")
            label = abbreviate_tool_input(tool_name, tool_input)

            el = ScreenElement(
                kind="tool_call",
                tool_name=tool_name,
                label=label,
                tool_use_id=tool_id,
                request_id=request_id,
            )
            state.elements.append(el)
            state.tool_calls[tool_id] = len(state.elements) - 1
        elif block_type == "thinking":
            state.elements.append(
                ScreenElement(kind="thinking", request_id=request_id)
            )


def _handle_system(state: ScreenState, line: dict) -> None:
    """Handle system-type messages."""
    subtype = line.get("subtype", "")

    if subtype == "turn_duration":
        duration_ms = line.get("durationMs", 0)
        state.elements.append(
            ScreenElement(kind="turn_duration", duration_ms=duration_ms)
        )
    elif subtype == "compact_boundary":
        # Clear all content from state
        state.elements.clear()
        state.tool_calls.clear()
        state.current_request_id = None
    # local_command is invisible


def _handle_progress(state: ScreenState, line: dict) -> None:
    """Handle progress-type messages."""
    data = line.get("data", {})
    progress_type = data.get("type", "")
    parent_tool_use_id = line.get("parentToolUseID", "")

    # Find matching tool call element
    el: ScreenElement | None = None
    if parent_tool_use_id and parent_tool_use_id in state.tool_calls:
        idx = state.tool_calls[parent_tool_use_id]
        el = state.elements[idx]

    # Don't overwrite results that have been finalized by a tool_result
    if el is not None and el.result_is_final:
        return

    if progress_type == "bash_progress":
        if el is not None:
            output = data.get("output", "")
            el.result = output
    elif progress_type == "agent_progress":
        if el is not None:
            el.result = "Agent: working\u2026"
    elif progress_type == "hook_progress":
        hook_name = data.get("hookName", "")
        if el is not None:
            el.result = f"Hook: {hook_name}"
    elif progress_type == "query_update":
        query = data.get("query", "")
        if el is not None:
            el.result = f"Searching: {query}"
    elif progress_type == "search_results_received":
        result_count = data.get("resultCount", 0)
        if el is not None:
            el.result = f"{result_count} results"
    elif progress_type == "waiting_for_task":
        task_desc = data.get("taskDescription", "")
        if el is not None:
            el.result = f"Waiting: {task_desc}"
