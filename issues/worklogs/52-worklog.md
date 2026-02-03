# Issue #52: Add stateless session transformer function

## Summary

Implemented `transform()` function that converts JSONL lines into events with explicit state threading. The original context is never mutated, making it suitable for the watcher service's state persistence requirements.

## Changes Made

### New Files

1. **`claude_session_player/watcher/transformer.py`**
   - `transform(lines, context)` function that:
     - Deep copies the input context to avoid mutation
     - Saves and restores module-level caches (`_tool_content_cache`, `_question_content_cache`) for isolation
     - Processes all lines through `process_line()`
     - Returns tuple of `(events, new_context)`
   - Pure function: no side effects, no I/O

2. **`tests/watcher/test_transformer.py`**
   - 28 comprehensive tests covering all acceptance criteria

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added export for `transform` function

## Design Decisions

### Option A: Deep Copy Context

As recommended in the issue, used deep copy approach for minimal changes to existing code:

```python
def transform(lines, context):
    ctx = copy.deepcopy(context)
    # ... process lines ...
    return events, ctx
```

This approach:
- Keeps existing `process_line()` unchanged
- Simple and predictable
- Slight performance cost for deep copy (acceptable for watcher use case)

### Module Cache Isolation

The existing `processor.py` uses module-level caches (`_tool_content_cache`, `_question_content_cache`) that aren't part of `ProcessingContext`. To ensure true statelessness, the transformer:

1. Saves the current cache state before processing
2. Clears the caches for a fresh start
3. Processes all lines
4. Restores the original cache state in a `finally` block

This ensures:
- Multiple concurrent `transform()` calls don't interfere
- External code using `process_line()` directly isn't affected
- Each `transform()` call gets clean cache state

## Test Coverage

28 tests organized by functionality:

- **TestTransformBasic** (2 tests): Empty lines behavior
- **TestTransformImmutability** (4 tests): Original context unchanged
- **TestTransformEventGeneration** (7 tests): Correct events for each line type
- **TestTransformToolLinking** (3 tests): tool_use → tool_result matching
- **TestTransformMultipleLines** (3 tests): Event accumulation
- **TestTransformContextCompaction** (2 tests): ClearAll handling
- **TestTransformProgressMessages** (2 tests): Bash/hook/agent progress
- **TestTransformParityWithProcessLine** (2 tests): Output matches direct process_line
- **TestTransformCacheIsolation** (3 tests): Module cache isolation

## Test Results

- **Before:** 585 tests total
- **After:** 613 tests total (28 new)
- All tests pass (excluding 2 unrelated slack tests that fail due to missing optional dependency)

## Acceptance Criteria Status

- [x] `transform()` returns events and new context
- [x] Original context is not mutated
- [x] Output events match `process_line()` behavior exactly
- [x] Works with empty line list
- [x] Handles `ClearAll` event (context compaction)

## Testing DoD Status

- [x] Test transform with various line types produces correct events
- [x] Test original context unchanged after transform
- [x] Test empty lines list returns empty events, same context
- [x] Test context compaction resets returned context
- [x] Test tool_use followed by tool_result links correctly
- [x] Test multiple lines accumulate events correctly
- [x] Compare output against existing `process_line()` for parity

## Spec Reference

Implements § Session Transformer from `.claude/specs/session-watcher-service.md`.
