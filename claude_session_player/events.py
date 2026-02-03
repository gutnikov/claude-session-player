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

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "type": "user",
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> UserContent:
        """Deserialize from dictionary."""
        return cls(text=data["text"])


@dataclass
class AssistantContent:
    """Content for assistant response blocks."""

    text: str

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "type": "assistant",
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AssistantContent:
        """Deserialize from dictionary."""
        return cls(text=data["text"])


@dataclass
class ToolCallContent:
    """Content for tool call blocks."""

    tool_name: str
    tool_use_id: str
    label: str
    result: str | None = None
    is_error: bool = False
    progress_text: str | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "type": "tool_call",
            "tool_name": self.tool_name,
            "tool_use_id": self.tool_use_id,
            "label": self.label,
            "result": self.result,
            "is_error": self.is_error,
            "progress_text": self.progress_text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ToolCallContent:
        """Deserialize from dictionary."""
        return cls(
            tool_name=data["tool_name"],
            tool_use_id=data["tool_use_id"],
            label=data["label"],
            result=data.get("result"),
            is_error=data.get("is_error", False),
            progress_text=data.get("progress_text"),
        )


@dataclass
class ThinkingContent:
    """Content for thinking indicator blocks."""

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {"type": "thinking"}

    @classmethod
    def from_dict(cls, data: dict) -> ThinkingContent:
        """Deserialize from dictionary."""
        return cls()


@dataclass
class DurationContent:
    """Content for turn duration blocks."""

    duration_ms: int

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "type": "duration",
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DurationContent:
        """Deserialize from dictionary."""
        return cls(duration_ms=data["duration_ms"])


@dataclass
class SystemContent:
    """Content for system output blocks."""

    text: str

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "type": "system",
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SystemContent:
        """Deserialize from dictionary."""
        return cls(text=data["text"])


@dataclass
class QuestionOption:
    """A single option for a question."""

    label: str
    description: str

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "label": self.label,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> QuestionOption:
        """Deserialize from dictionary."""
        return cls(
            label=data["label"],
            description=data["description"],
        )


@dataclass
class Question:
    """A single question with options."""

    question: str
    header: str
    options: list[QuestionOption]
    multi_select: bool = False

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "question": self.question,
            "header": self.header,
            "options": [opt.to_dict() for opt in self.options],
            "multi_select": self.multi_select,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Question:
        """Deserialize from dictionary."""
        return cls(
            question=data["question"],
            header=data["header"],
            options=[QuestionOption.from_dict(opt) for opt in data["options"]],
            multi_select=data.get("multi_select", False),
        )


@dataclass
class QuestionContent:
    """Content for AskUserQuestion tool blocks."""

    tool_use_id: str
    questions: list[Question]
    answers: dict[str, str] | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "type": "question",
            "tool_use_id": self.tool_use_id,
            "questions": [q.to_dict() for q in self.questions],
            "answers": self.answers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> QuestionContent:
        """Deserialize from dictionary."""
        return cls(
            tool_use_id=data["tool_use_id"],
            questions=[Question.from_dict(q) for q in data["questions"]],
            answers=data.get("answers"),
        )


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


def content_from_dict(data: dict) -> BlockContent:
    """Deserialize BlockContent from dictionary using type discriminator.

    Routes to the correct from_dict method based on the "type" field.

    Args:
        data: Dictionary with "type" field indicating content type.

    Returns:
        The appropriate BlockContent subclass instance.

    Raises:
        KeyError: If "type" field is missing or unknown.
    """
    type_map = {
        "user": UserContent.from_dict,
        "assistant": AssistantContent.from_dict,
        "tool_call": ToolCallContent.from_dict,
        "question": QuestionContent.from_dict,
        "thinking": ThinkingContent.from_dict,
        "duration": DurationContent.from_dict,
        "system": SystemContent.from_dict,
    }
    return type_map[data["type"]](data)


# --- Block ---


@dataclass
class Block:
    """A renderable block with explicit identity."""

    id: str
    type: BlockType
    content: BlockContent
    request_id: str | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content.to_dict(),
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Block:
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            type=BlockType(data["type"]),
            content=content_from_dict(data["content"]),
            request_id=data.get("request_id"),
        )


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

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "tool_use_id_to_block_id": self.tool_use_id_to_block_id,
            "current_request_id": self.current_request_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProcessingContext:
        """Deserialize from dictionary."""
        return cls(
            tool_use_id_to_block_id=data.get("tool_use_id_to_block_id", {}),
            current_request_id=data.get("current_request_id"),
        )
