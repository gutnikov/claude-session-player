# Issue 01: Project Scaffolding & Models

## Priority: P0 — Foundation
## Dependencies: None
## Estimated Complexity: Medium

## Summary

Set up the Python project structure, dependencies, and core data models (`ScreenState`, `ScreenElement` variants). This is the foundation everything else builds on.

## Context

We are building a Claude Code session replay tool. The core API is:

```python
def render(state: ScreenState, line: dict) -> ScreenState
```

This issue creates the project skeleton and the data models that represent the screen state. No rendering logic yet — just the types and project infrastructure.

### Key Spec References
- See `.claude/specs/claude-session-player.md` — sections "API Design", "ScreenState Internal Structure", "Project Structure"
- See `claude-code-session-protocol-schema.md` — full protocol reference

## Detailed Requirements

### 1. Project Setup

Create a Python 3.12+ project with:

```
claude_session_player/
├── __init__.py          # Package init, version
├── models.py            # ScreenState, ScreenElement dataclasses
├── renderer.py          # Stub: render() function signature only
├── formatter.py         # Stub: to_markdown() only
├── parser.py            # Stub: JSONL reading signature only
├── tools.py             # Stub: tool abbreviation signatures only
└── cli.py               # Stub: CLI entry point

tests/
├── __init__.py
├── test_models.py       # Tests for this issue
├── conftest.py          # Shared fixtures
└── fixtures/            # Test data directory
```

### 2. pyproject.toml

```toml
[project]
name = "claude-session-player"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

No external runtime dependencies. Only stdlib. Dev deps: pytest.

### 3. ScreenElement Models

Create as dataclasses (not Pydantic — no external deps needed for simple data containers):

```python
from dataclasses import dataclass, field
from typing import Literal

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
    tool_use_id: str          # For matching results back
    label: str                # Abbreviated input display
    result: str | None = None # Filled when tool_result arrives
    is_error: bool = False    # True if tool_result had is_error=true
    progress_text: str | None = None  # Updated by progress messages

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
ScreenElement = UserMessage | AssistantText | ToolCall | ThinkingIndicator | TurnDuration | SystemOutput
```

### 4. ScreenState Model

```python
@dataclass
class ScreenState:
    """Mutable state representing the current terminal screen."""
    elements: list[ScreenElement] = field(default_factory=list)
    tool_calls: dict[str, int] = field(default_factory=dict)
    # tool_use_id → index in elements list, for result/progress lookups
    current_request_id: str | None = None
    # Tracks the current assistant response group for merging

    def to_markdown(self) -> str:
        """Render current state as markdown text."""
        raise NotImplementedError("Implemented in issue 03-04")

    def clear(self) -> None:
        """Clear all state (used on compaction)."""
        self.elements.clear()
        self.tool_calls.clear()
        self.current_request_id = None
```

### 5. Tests for Models

Write tests verifying:
- `ScreenState()` initializes with empty elements, empty tool_calls, None request_id
- `ScreenState.clear()` resets all fields
- All `ScreenElement` variants can be instantiated with correct fields
- `ToolCall` defaults: `result=None`, `is_error=False`, `progress_text=None`
- `tool_calls` dict correctly maps string IDs to integer indices
- Elements list maintains insertion order
- Type narrowing works: `isinstance(element, ToolCall)` etc.

## Definition of Done

- [ ] `pyproject.toml` created with correct metadata, no runtime deps, pytest in dev deps
- [ ] All files in project structure created (stubs for unimplemented modules)
- [ ] `ScreenState` dataclass with `elements`, `tool_calls`, `current_request_id` fields
- [ ] `clear()` method on ScreenState works
- [ ] All 6 `ScreenElement` variant dataclasses created with correct fields
- [ ] `ScreenElement` union type defined
- [ ] `tests/test_models.py` with ≥10 tests, all passing
- [ ] `pytest` runs successfully from project root
- [ ] `conftest.py` created with shared fixtures (at minimum: `empty_state` fixture)

## Worklog

After completing this issue, write `issues/worklogs/01-worklog.md` containing:
- Exact files created with brief description
- Any deviations from the spec (field names, types, etc.)
- Test count and results
- Decisions made (e.g., if you chose `__slots__` or frozen dataclasses, explain why)
