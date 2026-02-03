# Issue 26 Worklog: Core Event Model

## Summary

Implemented the foundational data structures for the event-driven renderer: Block, BlockType, BlockContent variants, Event types, and ProcessingContext. This is Phase 1 of the event-driven renderer specification.

## Files Created

| File | Description |
|------|-------------|
| `claude_session_player/events.py` | All new types: Block, BlockType, 6 BlockContent variants, 3 Event types, ProcessingContext |
| `tests/test_events.py` | 35 unit tests covering all types |

## Implementation Details

### BlockType Enum (6 values)

```python
class BlockType(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    THINKING = "thinking"
    DURATION = "duration"
    SYSTEM = "system"
```

### BlockContent Types (6 dataclasses)

1. `UserContent(text: str)` - User input text
2. `AssistantContent(text: str)` - Assistant response text
3. `ToolCallContent(tool_name, tool_use_id, label, result?, is_error?, progress_text?)` - Tool invocation with optional result
4. `ThinkingContent()` - Thinking indicator (no fields)
5. `DurationContent(duration_ms: int)` - Turn duration
6. `SystemContent(text: str)` - System/orphan output

### Block

```python
@dataclass
class Block:
    id: str                          # Unique identifier
    type: BlockType                  # Enum value
    content: BlockContent            # Type-specific content
    request_id: str | None = None    # For grouping related blocks
```

### Event Types (3)

1. `AddBlock(block: Block)` - Append a new block
2. `UpdateBlock(block_id: str, content: BlockContent)` - Update existing block
3. `ClearAll()` - Clear all blocks (compaction)

### ProcessingContext

```python
@dataclass
class ProcessingContext:
    tool_use_id_to_block_id: dict[str, str]  # Map tool_use_id → block_id
    current_request_id: str | None = None

    def clear(self) -> None:
        # Resets both fields
```

## Test Summary

| Test Class | Test Count | Coverage |
|------------|------------|----------|
| `TestBlockType` | 7 | All 6 enum values + count check |
| `TestBlockContent` | 8 | All 6 content types, including ToolCallContent variants |
| `TestBlock` | 8 | Creation, defaults, equality, all content type combinations |
| `TestEvents` | 6 | AddBlock, UpdateBlock, ClearAll, union type acceptance |
| `TestProcessingContext` | 6 | Init, storage, clear(), idempotency |
| **Total** | **35** | All types fully covered |

## Test Results

```
376 passed in 10.41s
```

- 341 existing tests: all pass (no regressions)
- 35 new tests: all pass

## Decisions Made

1. **File location**: Created `events.py` in `claude_session_player/` as specified, keeping all event-driven types together.

2. **Union type syntax**: Used `Union[...]` from typing for Python 3.9 compatibility (the project runs on 3.9.6 per pytest output), though the spec suggests 3.12+. The `from __future__ import annotations` enables `str | None` syntax for type hints.

3. **Minimal implementation**: Followed the issue specification exactly - no extra methods or features beyond what was specified.

4. **No changes to existing code**: This is an additive-only change as required by the Definition of Done.

## Deviations from Spec

None. The implementation matches the issue specification exactly.

## Definition of Done Checklist

- [x] All types defined in `events.py`
- [x] Full type hints on all dataclasses
- [x] ≥10 unit tests, all passing (35 tests)
- [x] No changes to existing code (additive only)
