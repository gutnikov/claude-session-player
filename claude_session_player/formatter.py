"""Markdown formatting for screen elements."""

from __future__ import annotations

from claude_session_player.models import ScreenElement

MAX_RESULT_LINES = 5


def _format_user_message(el: ScreenElement) -> str:
    """Format a user message with prompt prefix."""
    lines = el.text.split("\n")
    if not lines or (len(lines) == 1 and not lines[0]):
        return "\u276f"
    result_lines = [f"\u276f {lines[0]}"]
    for line in lines[1:]:
        result_lines.append(f"  {line}")
    return "\n".join(result_lines)


def _format_assistant_text(el: ScreenElement) -> str:
    """Format assistant text with bullet prefix."""
    if not el.text:
        return "\u25cf"
    lines = el.text.split("\n")
    result_lines = [f"\u25cf {lines[0]}"]
    for line in lines[1:]:
        result_lines.append(f"  {line}")
    return "\n".join(result_lines)


def _truncate_result(text: str, max_lines: int = MAX_RESULT_LINES) -> tuple[str, bool]:
    """Truncate result text to max_lines. Returns (text, was_truncated)."""
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text, False
    # Keep max_lines - 1 lines, then add truncation indicator
    return "\n".join(lines[: max_lines - 1]), True


def _format_tool_call(el: ScreenElement) -> str:
    """Format a tool call with optional result."""
    header = f"\u25cf {el.tool_name}({el.label})"
    if el.result is None:
        return header

    result_text, truncated = _truncate_result(el.result)
    result_lines = result_text.split("\n")

    if el.is_error:
        prefix = "  \u2717 "
    else:
        prefix = "  \u2514 "

    formatted_result_lines = []
    for i, line in enumerate(result_lines):
        if i == 0:
            formatted_result_lines.append(f"{prefix}{line}")
        else:
            # Continuation lines get same indent but just spaces
            formatted_result_lines.append(f"    {line}")

    if truncated:
        formatted_result_lines.append("  \u2514 \u2026")

    return header + "\n" + "\n".join(formatted_result_lines)


def _format_thinking(el: ScreenElement) -> str:
    """Format thinking indicator."""
    return "\u2731 Thinking\u2026"


def _format_turn_duration(el: ScreenElement) -> str:
    """Format turn duration."""
    ms = el.duration_ms
    seconds = ms // 1000
    if seconds >= 60:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"\u2731 Crunched for {minutes}m {remaining_seconds}s"
    return f"\u2731 Crunched for {seconds}s"


def _format_system_output(el: ScreenElement) -> str:
    """Format system output."""
    return el.text


_FORMATTERS = {
    "user_message": _format_user_message,
    "assistant_text": _format_assistant_text,
    "tool_call": _format_tool_call,
    "thinking": _format_thinking,
    "turn_duration": _format_turn_duration,
    "system_output": _format_system_output,
}


def format_element(el: ScreenElement) -> str:
    """Format a single screen element to markdown."""
    formatter = _FORMATTERS.get(el.kind)
    if formatter is not None:
        return formatter(el)
    return ""


def format_elements(elements: list[ScreenElement], current_request_id: str | None) -> str:
    """Format all elements into markdown output.

    Elements are separated by blank lines, except consecutive elements
    that belong to the same assistant requestId group (no blank line between them).
    """
    if not elements:
        return ""

    parts: list[str] = []
    prev_request_id: str = ""

    for el in elements:
        formatted = format_element(el)
        if not formatted:
            continue

        el_request_id = el.request_id

        # Add blank line between top-level groups, but not within same requestId
        if parts:
            if el_request_id and prev_request_id and el_request_id == prev_request_id:
                # Same assistant response group: no blank line
                pass
            else:
                parts.append("")  # blank line separator

        parts.append(formatted)
        if el_request_id:
            prev_request_id = el_request_id
        else:
            prev_request_id = ""

    return "\n".join(parts)
