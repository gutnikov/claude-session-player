"""Event-driven renderer data model.

This module defines the core event model for the event-driven renderer:
- Block: A renderable block with explicit identity
- BlockType: Enum of block types
- BlockContent: Type-specific content dataclasses
- Event: AddBlock, UpdateBlock, ClearAll
- ProcessingContext: Minimal state needed during processing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Union


class BlockType(Enum):
    """Types of renderable blocks."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    QUESTION = "question"
    THINKING = "thinking"
    DURATION = "duration"
    SYSTEM = "system"


# --- BlockContent types ---


@dataclass
class UserContent:
    """Content for user input blocks."""

    text: str


@dataclass
class AssistantContent:
    """Content for assistant response blocks."""

    text: str


@dataclass
class ToolCallContent:
    """Content for tool call blocks."""

    tool_name: str
    tool_use_id: str
    label: str
    result: str | None = None
    is_error: bool = False
    progress_text: str | None = None


@dataclass
class ThinkingContent:
    """Content for thinking indicator blocks."""

    pass


@dataclass
class DurationContent:
    """Content for turn duration blocks."""

    duration_ms: int


@dataclass
class SystemContent:
    """Content for system output blocks."""

    text: str


@dataclass
class QuestionOption:
    """A single option for a question."""

    label: str
    description: str


@dataclass
class Question:
    """A single question with options."""

    question: str
    header: str
    options: list[QuestionOption]
    multi_select: bool = False


@dataclass
class QuestionContent:
    """Content for AskUserQuestion tool blocks."""

    tool_use_id: str
    questions: list[Question]
    answers: dict[str, str] | None = None


# Union type for all block content types
BlockContent = Union[
    UserContent,
    AssistantContent,
    ToolCallContent,
    QuestionContent,
    ThinkingContent,
    DurationContent,
    SystemContent,
]


# --- Block ---


@dataclass
class Block:
    """A renderable block with explicit identity."""

    id: str
    type: BlockType
    content: BlockContent
    request_id: str | None = None


# --- Event types ---


@dataclass
class AddBlock:
    """Append a new block to the conversation."""

    block: Block


@dataclass
class UpdateBlock:
    """Update an existing block's content."""

    block_id: str
    content: BlockContent


@dataclass
class ClearAll:
    """Clear all blocks (compaction boundary)."""

    pass


# Union type for all event types
Event = Union[AddBlock, UpdateBlock, ClearAll]


# --- ProcessingContext ---


@dataclass
class ProcessingContext:
    """Minimal state needed during processing."""

    tool_use_id_to_block_id: dict[str, str] = field(default_factory=dict)
    current_request_id: str | None = None

    def clear(self) -> None:
        """Reset all context state."""
        self.tool_use_id_to_block_id.clear()
        self.current_request_id = None
