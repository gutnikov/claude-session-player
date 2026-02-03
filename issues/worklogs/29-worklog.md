# Issue 29 Worklog: CLI Integration & Migration

## Summary

Updated the CLI and `replay-session.sh` to use the new event-driven flow. This is Phase 4 of the event-driven renderer specification, completing the migration from mutable-state to event-driven rendering.

## Files Modified

| File | Description |
|------|-------------|
| `claude_session_player/cli.py` | Replaced old mutable-state render loop with event-driven `replay_session()` |
| `claude_session_player/__init__.py` | Added clean public API exports for all event-driven types |
| `bin/replay-session.sh` | Updated inline Python to use `replay_session()` from consumer |
| `claude_session_player/processor.py` | Bug fix: update cache after tool result to preserve result through progress updates |
| `tests/test_integration.py` | Major expansion: 39 tests (up from ~20) covering CLI, scripts, API comparison |

## Implementation Details

### CLI Changes

**Before:**
```python
from .models import ScreenState
from .parser import read_session
from .renderer import render

lines = read_session(path)
state = ScreenState()
for line in lines:
    render(state, line)
print(state.to_markdown())
```

**After:**
```python
from .consumer import replay_session
from .parser import read_session

lines = read_session(path)
print(replay_session(lines))
```

### Public API Exports

Added to `__init__.py`:
- Events: `Block`, `BlockType`, `BlockContent`, `UserContent`, `AssistantContent`, `ToolCallContent`, `ThinkingContent`, `DurationContent`, `SystemContent`, `AddBlock`, `UpdateBlock`, `ClearAll`, `Event`, `ProcessingContext`
- Processor: `process_line`
- Consumer: `ScreenStateConsumer`, `replay_session`
- Parser: `read_session`, `classify_line`, `LineType`

### Bug Fix: Tool Result Persistence

Discovered a bug where tool results were not persisted through subsequent progress updates. When a `TOOL_RESULT` arrived followed by `HOOK_PROGRESS`, the progress would overwrite the result because the cache wasn't updated.

**Fix:** Update `_tool_content_cache` in `_process_tool_result()` after creating the updated content:
```python
_store_tool_content(tool_use_id, updated_content)
```

This ensures subsequent progress messages preserve the result field.

## Test Summary

| Test Class | Test Count | Coverage |
|------------|------------|----------|
| `TestSnapshotSayHi` | 1 | Snapshot: simple session |
| `TestSnapshotTrelloCleanup` | 1 | Snapshot: tools, thinking, turns |
| `TestSnapshotBootstrapPlugin` | 1 | Snapshot: local command output |
| `TestSnapshotTaskSubagent` | 1 | Snapshot: Task tool collapsed result |
| `TestSnapshotProtoMigrationCompaction` | 1 | Snapshot: compaction |
| `TestOldVsNewAPIComparison` | 5 | Byte-for-byte identical output verification |
| `TestNoCrash` | 3 | All sessions, subagents, stress test |
| `TestScenario*` | 10 | Various scenario tests using new API |
| `TestEmptySession` | 2 | Empty and invisible-only sessions |
| `TestCompactionOnlyShowsPostCompaction` | 1 | Compaction clears pre-compaction |
| `TestCLI` | 5 | CLI with valid file, missing args, errors, module invocation, empty file |
| `TestReplaySessionScript` | 5 | Shell script tests: exists, usage, file not found, valid file, line limit |
| `TestPublicAPI` | 3 | Package imports, replay_session, explicit event flow |
| **Total** | **39** | Comprehensive CLI and integration coverage |

## Test Results

```
459 passed in 21.15s
```

- 441 existing tests: all pass (no regressions)
- 18 new tests in test_integration.py (39 total vs ~20 before)
- All snapshot tests produce identical output with new API

## Decisions Made

1. **Minimal CLI changes**: Only replaced the render loop with `replay_session()`, keeping the same argument handling and error messages.

2. **Clean public API**: Exported all event types, processor, consumer, and parser functions for users who want the explicit event-driven flow.

3. **Preserved backward compatibility**: The old API (`ScreenState`, `render`) still works and is tested against the new API for identical output.

4. **Shell script updated**: Changed inline Python to use `replay_session()` instead of the old mutable-state pattern.

## Deviations from Spec

1. **Bug fix in processor.py**: Added cache update in `_process_tool_result()` to fix tool result persistence through progress updates. This was discovered during stress testing - not part of the original issue but necessary for correct output.

## Definition of Done Checklist

- [x] cli.py uses event-driven flow
- [x] replay-session.sh works unchanged (uses updated inline Python)
- [x] All snapshot tests pass with identical output
- [x] All stress tests pass
- [x] All integration tests pass
- [x] ≥10 integration tests covering CLI and scripts (39 tests)
- [x] Public API exports are clean and documented
