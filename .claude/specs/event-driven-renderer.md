# Event-Driven Renderer Specification

## Overview

Transform the claude-session-player from a mutable-state model to an **event-driven incremental model**. Instead of maintaining a full `ScreenState` that gets mutated, the renderer emits discrete events that signal adding or updating blocks.

## Goals

1. **Incremental updates** — Consumers receive precise change notifications instead of diffing full state
2. **Explicit block identity** — Every block has a unique ID for reliable updates
3. **Backwards compatibility** — Existing CLI/scripts continue to work via a state-building consumer
4. **Clean separation** — Renderer emits events, consumers decide how to handle them

## Architecture

```
JSONL Line
    ↓
classify_line() → LineType (unchanged)
    ↓
process_line(context, line) → list[Event]
    ↓
Consumer handles events
    ├─ ScreenStateConsumer (builds full state, for CLI)
    ├─ StreamingConsumer (prints incrementally)
    └─ UIConsumer (updates DOM/TUI)
```

## Core Data Model

### Block (replaces ScreenElement)

```python
@dataclass
class Block:
    """A renderable block with explicit identity."""
    id: str                          # Unique identifier (UUID or derived)
    type: BlockType                  # Enum: USER, ASSISTANT, TOOL_CALL, THINKING, DURATION, SYSTEM
    content: BlockContent            # Type-specific content dataclass
    request_id: str | None = None    # For grouping related blocks
```

### BlockType Enum

```python
class BlockType(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    QUESTION = "question"      # AskUserQuestion tool
    THINKING = "thinking"
    DURATION = "duration"
    SYSTEM = "system"
```

### BlockContent Union

```python
@dataclass
class UserContent:
    text: str

@dataclass
class AssistantContent:
    text: str

@dataclass
class ToolCallContent:
    tool_name: str
    tool_use_id: str
    label: str
    result: str | None = None
    is_error: bool = False
    progress_text: str | None = None

@dataclass
class ThinkingContent:
    pass  # No additional data needed

@dataclass
class DurationContent:
    duration_ms: int

@dataclass
class SystemContent:
    text: str

@dataclass
class QuestionOption:
    label: str
    description: str

@dataclass
class Question:
    question: str
    header: str
    options: list[QuestionOption]
    multi_select: bool = False

@dataclass
class QuestionContent:
    tool_use_id: str
    questions: list[Question]
    answers: dict[str, str] | None = None  # Filled when user responds

BlockContent = UserContent | AssistantContent | ToolCallContent | QuestionContent | ThinkingContent | DurationContent | SystemContent
```

### Events

```python
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

Event = AddBlock | UpdateBlock | ClearAll
```

### ProcessingContext

```python
@dataclass
class ProcessingContext:
    """Minimal state needed during processing."""
    tool_use_id_to_block_id: dict[str, str]  # Map tool_use_id → block_id
    current_request_id: str | None = None

    def clear(self) -> None:
        self.tool_use_id_to_block_id.clear()
        self.current_request_id = None
```

## Event Emission Rules

### Adding Blocks

| Line Type | Event | Block ID Generation |
|-----------|-------|---------------------|
| USER_INPUT | AddBlock(USER) | `uuid4()` |
| LOCAL_COMMAND_OUTPUT | AddBlock(SYSTEM) | `uuid4()` |
| ASSISTANT_TEXT | AddBlock(ASSISTANT) | `uuid4()` |
| TOOL_USE | AddBlock(TOOL_CALL) | `uuid4()` (store mapping: tool_use_id → block_id) |
| TOOL_USE (AskUserQuestion) | AddBlock(QUESTION) | `uuid4()` (store mapping: tool_use_id → block_id) |
| THINKING | AddBlock(THINKING) | `uuid4()` |
| TURN_DURATION | AddBlock(DURATION) | `uuid4()` |
| Orphan TOOL_RESULT | AddBlock(SYSTEM) | `uuid4()` |

### Updating Blocks

| Line Type | Condition | Event |
|-----------|-----------|-------|
| TOOL_RESULT | tool_use_id in mapping (ToolCall) | UpdateBlock(block_id, updated ToolCallContent) |
| TOOL_RESULT | tool_use_id in mapping (Question) | UpdateBlock(block_id, updated QuestionContent with answers) |
| BASH_PROGRESS | parent_tool_use_id in mapping | UpdateBlock(block_id, updated ToolCallContent) |
| HOOK_PROGRESS | parent_tool_use_id in mapping | UpdateBlock(block_id, updated ToolCallContent) |
| AGENT_PROGRESS | parent_tool_use_id in mapping | UpdateBlock(block_id, updated ToolCallContent) |
| QUERY_UPDATE | parent_tool_use_id in mapping | UpdateBlock(block_id, updated ToolCallContent) |
| SEARCH_RESULTS | parent_tool_use_id in mapping | UpdateBlock(block_id, updated ToolCallContent) |
| WAITING_FOR_TASK | parent_tool_use_id in mapping | UpdateBlock(block_id, updated ToolCallContent) |

### Clearing

| Line Type | Event |
|-----------|-------|
| COMPACT_BOUNDARY | ClearAll() |

## Consumers

### ScreenStateConsumer (Reference Implementation)

Builds a full state from events, providing backwards compatibility:

```python
class ScreenStateConsumer:
    """Builds full conversation state from events."""

    def __init__(self):
        self.blocks: list[Block] = []
        self._block_index: dict[str, int] = {}  # block_id → index

    def handle(self, event: Event) -> None:
        if isinstance(event, AddBlock):
            self._block_index[event.block.id] = len(self.blocks)
            self.blocks.append(event.block)
        elif isinstance(event, UpdateBlock):
            index = self._block_index[event.block_id]
            self.blocks[index].content = event.content
        elif isinstance(event, ClearAll):
            self.blocks.clear()
            self._block_index.clear()

    def to_markdown(self) -> str:
        # Format blocks with request_id grouping (same logic as current formatter)
        ...
```

### Integration with CLI

```python
def main():
    lines = read_session(path)
    context = ProcessingContext()
    consumer = ScreenStateConsumer()

    for line in lines:
        events = process_line(context, line)
        for event in events:
            consumer.handle(event)

    print(consumer.to_markdown())
```

## Implementation Phases

### Phase 1: Core Event Model
- Define Block, BlockType, BlockContent dataclasses
- Define Event types (AddBlock, UpdateBlock, ClearAll)
- Define ProcessingContext
- Unit tests for all dataclasses

### Phase 2: Event Processor
- Implement `process_line(context, line) -> list[Event]`
- Reuse existing `classify_line()` and field extraction from parser.py
- Reuse `abbreviate_tool_input()` from tools.py
- Unit tests for each line type → event mapping

### Phase 3: ScreenStateConsumer
- Implement consumer that builds full block list from events
- Implement `to_markdown()` with request_id grouping
- Unit tests for event handling and markdown output

### Phase 4: Integration & Migration
- Update CLI to use new event-driven flow
- Ensure replay-session.sh still works
- Run all existing integration tests
- Add new integration tests for event flow

### Phase 5: Cleanup
- Remove old ScreenState/ScreenElement if no longer needed
- Update documentation (README, CLAUDE.md)
- Final validation with stress tests

## File Structure

```
claude_session_player/
├── models.py           # Block, BlockType, BlockContent, Event types
├── context.py          # ProcessingContext (new)
├── processor.py        # process_line() function (new, replaces renderer.py logic)
├── consumer.py         # ScreenStateConsumer (new)
├── formatter.py        # format_block(), to_markdown() (updated)
├── parser.py           # Unchanged (classify_line, field extraction)
├── tools.py            # Unchanged (abbreviate_tool_input)
└── cli.py              # Updated to use event-driven flow
```

## Backwards Compatibility

The public API changes but provides equivalent functionality:

**Before:**
```python
state = ScreenState()
for line in lines:
    render(state, line)
print(state.to_markdown())
```

**After:**
```python
context = ProcessingContext()
consumer = ScreenStateConsumer()
for line in lines:
    for event in process_line(context, line):
        consumer.handle(event)
print(consumer.to_markdown())
```

A convenience function can preserve the old API if needed:

```python
def replay_session(lines: list[dict]) -> str:
    """Convenience function matching old API."""
    context = ProcessingContext()
    consumer = ScreenStateConsumer()
    for line in lines:
        for event in process_line(context, line):
            consumer.handle(event)
    return consumer.to_markdown()
```

## AskUserQuestion Rendering

When Claude asks the user a question via `AskUserQuestion` tool:

**Pending (no answer yet):**
```
● Question: Pkg manager
  ├ How should we manage dependencies?
  │ ○ uv (Recommended)
  │ ○ poetry
  │ ○ pip + requirements.txt
  └ (awaiting response)
```

**Answered:**
```
● Question: Pkg manager
  ├ How should we manage dependencies?
  └ ✓ uv (Recommended)
```

The answer comes from `toolUseResult.answers` in the tool_result message.

## Success Criteria

1. All existing tests pass (possibly with API updates)
2. replay-session.sh produces identical output
3. Stress tests pass with same performance
4. Event stream can be consumed incrementally
5. No regression in markdown output formatting
6. AskUserQuestion tool calls render with questions and answers
