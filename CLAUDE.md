# CLAUDE.md - Claude Code Context for Claude Session Player

## Project Overview

Claude Session Player is a Python tool that replays Claude Code JSONL session files as readable markdown output. It processes session history line-by-line through a stateful render function, converting the raw protocol data into human-readable terminal-style output.

## Quick Commands

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -xvs

# Run with coverage report
pytest --cov=claude_session_player --cov-report=term-missing

# Replay a session file
claude-session-player examples/projects/orca/sessions/014d9d94-xxx.jsonl

# Or via Python module
python -m claude_session_player.cli path/to/session.jsonl
```

## Architecture

### Core Flow

```
JSONL line → classify_line() → render(state, line) → state.to_markdown()
```

1. **Parser** (`parser.py`): Reads JSONL, classifies lines into 15 `LineType` variants
2. **Renderer** (`renderer.py`): Dispatches to type-specific handlers, mutates `ScreenState`
3. **Formatter** (`formatter.py`): Converts `ScreenState` to markdown string
4. **Models** (`models.py`): `ScreenState` and 6 `ScreenElement` dataclasses

### Key Data Structures

```python
# Screen state holds all rendered elements
ScreenState:
    elements: list[ScreenElement]     # Ordered visual elements
    tool_calls: dict[str, int]        # tool_use_id → index for result matching
    current_request_id: str | None    # Groups consecutive assistant blocks

# Element types
UserMessage(text)                     # ❯ user input
AssistantText(text, request_id)       # ● response text
ToolCall(tool_name, tool_use_id, label, result, is_error, progress_text, request_id)
ThinkingIndicator(request_id)         # ✱ Thinking…
TurnDuration(duration_ms)             # ✱ Crunched for Xm Ys
SystemOutput(text)                    # Plain output
```

### Line Type Classification

```python
# User messages
USER_INPUT, TOOL_RESULT, LOCAL_COMMAND_OUTPUT

# Assistant messages
ASSISTANT_TEXT, TOOL_USE, THINKING

# System messages
TURN_DURATION, COMPACT_BOUNDARY

# Progress messages (update existing tool calls)
BASH_PROGRESS, HOOK_PROGRESS, AGENT_PROGRESS,
QUERY_UPDATE, SEARCH_RESULTS, WAITING_FOR_TASK

# Skip
INVISIBLE
```

## Coding Conventions

### Python Version

- Target Python 3.12+
- Use `from __future__ import annotations` for forward references
- Use `X | None` union syntax (not `Optional[X]`)
- Use dataclasses, not attrs or pydantic

### Style Guidelines

- No runtime dependencies (stdlib only)
- Simple if/elif chains (no match/case for 3.9 compat during testing)
- Table-driven dispatch preferred over long conditionals
- Defensive handling: unknown types → INVISIBLE, missing fields → empty/None

### Testing

- Tests in `tests/` directory
- Fixtures in `tests/conftest.py`
- Snapshot tests in `tests/snapshots/`
- All tests use pytest
- Target: comprehensive coverage (currently 99%)

## Important Patterns

### Tool Result Matching

Tool results match to tool calls via `tool_use_id`:

```python
# When tool_use is rendered:
state.tool_calls[tool_use_id] = len(state.elements) - 1

# When tool_result arrives:
if tool_use_id in state.tool_calls:
    index = state.tool_calls[tool_use_id]
    element = state.elements[index]
    element.result = truncate_result(content)
```

### Request ID Grouping

Consecutive assistant blocks with the same `requestId` render without blank lines between them:

```python
# In to_markdown():
if prev_request_id == current_request_id and current_request_id is not None:
    # No blank line
else:
    parts.append("")  # Blank line separator
```

### Context Compaction

When `compact_boundary` is encountered, clear all state:

```python
def _render_compact_boundary(state: ScreenState) -> None:
    state.clear()  # Removes all elements, tool_calls, resets request_id
```

### Sidechain Messages

Sub-agent messages have `isSidechain=True` and are classified as `INVISIBLE`:

```python
if line.get("isSidechain") and msg_type in ("user", "assistant"):
    return LineType.INVISIBLE
```

## File Locations

### Source Code
- `claude_session_player/models.py` - Data models
- `claude_session_player/parser.py` - JSONL parsing, line classification
- `claude_session_player/renderer.py` - Main render logic
- `claude_session_player/formatter.py` - Markdown output formatting
- `claude_session_player/tools.py` - Tool input abbreviation rules
- `claude_session_player/cli.py` - CLI entry point

### Tests
- `tests/test_models.py` - Model tests
- `tests/test_parser.py` - Parser tests
- `tests/test_renderer.py` - Renderer tests
- `tests/test_formatter.py` - Formatter tests
- `tests/test_tools.py` - Tool abbreviation tests
- `tests/test_integration.py` - Full session replay tests
- `tests/test_stress.py` - Stress tests with large sessions

### Example Data
- `examples/projects/*/sessions/*.jsonl` - Real session files
- `examples/projects/*/sessions/subagents/*.jsonl` - Sub-agent sessions
- `tests/snapshots/*.md` - Expected output snapshots

### Documentation
- `README.md` - User documentation
- `CLAUDE.md` - This file (Claude Code context)
- `.claude/specs/claude-session-player.md` - Original spec
- `claude-code-session-protocol-schema.md` - Protocol reference
- `issues/worklogs/*.md` - Development history

## Common Tasks

### Adding a New Message Type

1. Add variant to `LineType` enum in `parser.py`
2. Add classification logic in `classify_line()` or helper functions
3. Add handler in `renderer.py` following the `_render_*` pattern
4. Add formatting in `formatter.py` if needed
5. Add tests in appropriate test files

### Adding a New Tool

Add entry to `_TOOL_RULES` in `tools.py`:

```python
_TOOL_RULES = {
    # ...
    "NewTool": ("field_name", None, "truncate"),  # or "basename"
}
```

### Debugging Session Replay

```python
from claude_session_player.parser import read_session, classify_line, LineType

for i, line in enumerate(read_session("session.jsonl")):
    lt = classify_line(line)
    if lt != LineType.INVISIBLE:
        print(f"{i}: {lt.name} - {line.get('type')}")
```

## Known Limitations

1. **Subagent files produce empty output**: By design, `isSidechain=True` messages are invisible
2. **No streaming/animated output**: Output is static markdown
3. **No ANSI colors**: Plain text output only
4. **Orphan results**: Tool results from before compaction render as SystemOutput

## Protocol Notes

- Session protocol version: v2.0.76 – v2.1.29
- `parentToolUseID` is at top level of progress messages, not in `data`
- `toolUseResult` for Task tools is at top level, contains collapsed result
- Content can be string, list of blocks, or null
- List content may include non-text blocks (filter for `type: "text"`)
