"""Core data models for Claude Session Player."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


@dataclass
class UserMessage:
    """A user's input message. Rendered as ❯ text."""

    text: str


@dataclass
class AssistantText:
    """Assistant's text response. Rendered as ● text with markdown passthrough."""

    text: str


@dataclass
class ToolCall:
    """A tool invocation. Rendered as ● ToolName(label) with optional result."""

    tool_name: str
    tool_use_id: str
    label: str
    result: str | None = None
    is_error: bool = False
    progress_text: str | None = None


@dataclass
class ThinkingIndicator:
    """Thinking block. Rendered as ✱ Thinking…"""

    pass


@dataclass
class TurnDuration:
    """Turn timing. Rendered as ✱ Crunched for Xm Ys."""

    duration_ms: int


@dataclass
class SystemOutput:
    """System/local command output. Rendered as plain text."""

    text: str


# Union type for all screen elements
ScreenElement = Union[
    UserMessage, AssistantText, ToolCall, ThinkingIndicator, TurnDuration, SystemOutput
]


@dataclass
class ScreenState:
    """Mutable state representing the current terminal screen."""

    elements: list[ScreenElement] = field(default_factory=list)
    tool_calls: dict[str, int] = field(default_factory=dict)
    current_request_id: str | None = None

    def to_markdown(self) -> str:
        """Render current state as markdown text."""
        from .formatter import to_markdown

        return to_markdown(self)

    def clear(self) -> None:
        """Clear all state (used on compaction)."""
        self.elements.clear()
        self.tool_calls.clear()
        self.current_request_id = None
