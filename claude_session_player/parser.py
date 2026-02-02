"""JSONL session file parsing and line classification."""

from __future__ import annotations

import json
import logging
import re
from enum import Enum, auto
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Line classification enum
# ---------------------------------------------------------------------------


class LineType(Enum):
    # User
    USER_INPUT = auto()
    TOOL_RESULT = auto()
    LOCAL_COMMAND_OUTPUT = auto()

    # Assistant
    ASSISTANT_TEXT = auto()
    TOOL_USE = auto()
    THINKING = auto()

    # System
    TURN_DURATION = auto()
    COMPACT_BOUNDARY = auto()

    # Progress
    BASH_PROGRESS = auto()
    HOOK_PROGRESS = auto()
    AGENT_PROGRESS = auto()
    QUERY_UPDATE = auto()
    SEARCH_RESULTS = auto()
    WAITING_FOR_TASK = auto()

    # Skip
    INVISIBLE = auto()


# ---------------------------------------------------------------------------
# Always-invisible top-level types
# ---------------------------------------------------------------------------

_INVISIBLE_TYPES = frozenset({
    "file-history-snapshot",
    "queue-operation",
    "summary",
    "pr-link",
})

# ---------------------------------------------------------------------------
# Progress data.type → LineType mapping
# ---------------------------------------------------------------------------

_PROGRESS_MAP: dict[str, LineType] = {
    "bash_progress": LineType.BASH_PROGRESS,
    "hook_progress": LineType.HOOK_PROGRESS,
    "agent_progress": LineType.AGENT_PROGRESS,
    "query_update": LineType.QUERY_UPDATE,
    "search_results_received": LineType.SEARCH_RESULTS,
    "waiting_for_task": LineType.WAITING_FOR_TASK,
}

# ---------------------------------------------------------------------------
# System subtype → LineType mapping
# ---------------------------------------------------------------------------

_SYSTEM_MAP: dict[str, LineType] = {
    "turn_duration": LineType.TURN_DURATION,
    "compact_boundary": LineType.COMPACT_BOUNDARY,
    "local_command": LineType.INVISIBLE,
}

# ---------------------------------------------------------------------------
# Assistant content block type → LineType mapping
# ---------------------------------------------------------------------------

_ASSISTANT_BLOCK_MAP: dict[str, LineType] = {
    "text": LineType.ASSISTANT_TEXT,
    "tool_use": LineType.TOOL_USE,
    "thinking": LineType.THINKING,
}


# ---------------------------------------------------------------------------
# classify_line
# ---------------------------------------------------------------------------


def classify_line(line: dict) -> LineType:
    """Classify a parsed JSONL line into its rendering type."""
    msg_type = line.get("type")
    if msg_type is None:
        return LineType.INVISIBLE

    # Always-invisible types
    if msg_type in _INVISIBLE_TYPES:
        return LineType.INVISIBLE

    # User messages
    if msg_type == "user":
        return _classify_user(line)

    # Assistant messages
    if msg_type == "assistant":
        return _classify_assistant(line)

    # System messages
    if msg_type == "system":
        subtype = line.get("subtype", "")
        return _SYSTEM_MAP.get(subtype, LineType.INVISIBLE)

    # Progress messages
    if msg_type == "progress":
        data = line.get("data") or {}
        data_type = data.get("type", "")
        return _PROGRESS_MAP.get(data_type, LineType.INVISIBLE)

    # Unknown type
    return LineType.INVISIBLE


def _classify_user(line: dict) -> LineType:
    """Classify a user-type message."""
    if line.get("isMeta"):
        return LineType.INVISIBLE

    message = line.get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        if "<local-command-stdout>" in content:
            return LineType.LOCAL_COMMAND_OUTPUT
        return LineType.USER_INPUT

    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                return LineType.TOOL_RESULT
        return LineType.USER_INPUT

    # No content or unexpected shape
    return LineType.USER_INPUT


def _classify_assistant(line: dict) -> LineType:
    """Classify an assistant-type message."""
    message = line.get("message") or {}
    content = message.get("content")
    if not isinstance(content, list) or len(content) == 0:
        return LineType.INVISIBLE

    first_block = content[0]
    if not isinstance(first_block, dict):
        return LineType.INVISIBLE

    block_type = first_block.get("type", "")
    return _ASSISTANT_BLOCK_MAP.get(block_type, LineType.INVISIBLE)


# ---------------------------------------------------------------------------
# JSONL file reader
# ---------------------------------------------------------------------------


def read_session(path: str | Path) -> list[dict]:
    """Read a JSONL file and return list of parsed dicts.

    Skips empty lines and lines that fail JSON parsing (logs a warning).
    """
    path = Path(path)
    results: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    results.append(obj)
                else:
                    logger.warning("Line %d: expected dict, got %s", line_num, type(obj).__name__)
            except json.JSONDecodeError as exc:
                logger.warning("Line %d: failed to parse JSON: %s", line_num, exc)
    return results


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

_LOCAL_COMMAND_RE = re.compile(
    r"<local-command-stdout>(.*?)</local-command-stdout>", re.DOTALL
)


def get_user_text(line: dict) -> str:
    """Extract display text from a user input message."""
    message = line.get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text", "")
                if text:
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def get_tool_use_info(line: dict) -> tuple[str, str, dict]:
    """Extract (tool_name, tool_use_id, input_dict) from a tool_use message."""
    message = line.get("message") or {}
    content = message.get("content") or []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            return (
                block.get("name", ""),
                block.get("id", ""),
                block.get("input") or {},
            )
    return ("", "", {})


def get_tool_result_info(line: dict) -> list[tuple[str, str, bool]]:
    """Extract [(tool_use_id, content, is_error)] from a tool_result message."""
    message = line.get("message") or {}
    content = message.get("content") or []
    results: list[tuple[str, str, bool]] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            tool_use_id = block.get("tool_use_id", "")
            is_error = bool(block.get("is_error", False))
            block_content = block.get("content", "")
            if isinstance(block_content, str):
                text = block_content
            elif isinstance(block_content, list):
                text_parts = []
                for part in block_content:
                    if isinstance(part, dict):
                        text_parts.append(part.get("text", ""))
                text = "\n".join(text_parts)
            else:
                text = str(block_content)
            results.append((tool_use_id, text, is_error))
    return results


def get_request_id(line: dict) -> str | None:
    """Extract requestId from an assistant message."""
    return line.get("requestId")


def get_duration_ms(line: dict) -> int:
    """Extract durationMs from a turn_duration system message."""
    return line.get("durationMs", 0)


def get_progress_data(line: dict) -> dict:
    """Extract the data dict from a progress message."""
    return line.get("data") or {}


def get_parent_tool_use_id(line: dict) -> str | None:
    """Extract parentToolUseID from a progress message."""
    data = line.get("data") or {}
    return data.get("parentToolUseID")


def get_local_command_text(line: dict) -> str:
    """Extract text from <local-command-stdout> tags."""
    message = line.get("message") or {}
    content = message.get("content", "")
    if not isinstance(content, str):
        return ""
    match = _LOCAL_COMMAND_RE.search(content)
    return match.group(1) if match else ""
