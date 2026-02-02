"""Data models for Claude session player screen state."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScreenElement:
    """Tagged union for visual blocks on the terminal screen.

    The `kind` field determines which other fields are relevant:
    - "user_message": text
    - "assistant_text": text
    - "tool_call": tool_name, label, result, is_error, tool_use_id
    - "thinking": (no extra fields)
    - "turn_duration": duration_ms
    - "system_output": text
    """

    kind: str
    text: str = ""
    tool_name: str = ""
    label: str = ""
    result: str | None = None
    is_error: bool = False
    duration_ms: int = 0
    tool_use_id: str = ""
    request_id: str = ""  # Groups assistant content blocks from same API call
    result_is_final: bool = False  # True once a tool_result has set the result


@dataclass
class ScreenState:
    """Mutable screen state that accumulates rendered elements.

    Elements are appended as JSONL lines are processed. The same instance
    is mutated and returned by the render function.
    """

    elements: list[ScreenElement] = field(default_factory=list)
    tool_calls: dict[str, int] = field(default_factory=dict)
    current_request_id: str | None = None

    def to_markdown(self) -> str:
        """Render the current screen state as markdown text."""
        from claude_session_player.formatter import format_elements

        return format_elements(self.elements, self.current_request_id)
