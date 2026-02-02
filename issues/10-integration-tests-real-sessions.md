# Issue 10: Integration Tests with Real Sessions

## Priority: P1 — Validation
## Dependencies: All prior issues (01–09)
## Estimated Complexity: Medium

## Summary

Create comprehensive integration tests that process real JSONL session files from the `examples/` directory end-to-end, verifying the full pipeline works correctly and producing snapshot files of expected output.

## Context

Before starting, read:
- ALL worklogs: `issues/worklogs/01-worklog.md` through `issues/worklogs/09-worklog.md`

This is the final validation issue. We have unit tests for each component — now we need integration tests that prove the full `render` pipeline works on real session data.

### Key Spec References
- `.claude/specs/claude-session-player.md` — "Testing Approach"

## Detailed Requirements

### 1. Integration Test Framework

Create `tests/test_integration.py` with tests that:
1. Read a real JSONL file from `examples/`
2. Parse all lines
3. Fold through `render()` starting from empty `ScreenState`
4. Call `.to_markdown()` on final state
5. Compare against expected output (snapshot)

```python
def replay_session(jsonl_path: str) -> str:
    """Replay a full session and return markdown output."""
    lines = read_session(jsonl_path)
    state = ScreenState()
    for line in lines:
        render(state, line)
    return state.to_markdown()
```

### 2. Test Session Selection

Pick 5-8 real sessions from `examples/` that cover different scenarios:

| Session | Features Covered |
|---|---|
| Simple "say hi" session | Basic user → assistant text flow |
| Trello cleanup session | Tool use (Bash), tool results, thinking, multiple turns |
| Bootstrap plugin session | Local command output |
| Session with compaction | Summary + compact_boundary |
| Session with parallel tools | Multiple tool_use with same requestId |
| Session with sub-agent | Task tool use with collapsed result |
| Session with WebSearch | query_update, search_results_received progress |
| Long session with many turns | Stress test, verify no crashes |

### 3. Snapshot Testing

For each selected session:
1. Generate the markdown output
2. Manually review it for correctness
3. Save as `tests/snapshots/{session_name}.md`
4. Test asserts output matches snapshot

```python
def test_simple_session():
    output = replay_session("examples/projects/-Users-.../37dfb8a0-....jsonl")
    expected = read_snapshot("tests/snapshots/simple_say_hi.md")
    assert output == expected
```

### 4. No-Crash Tests

For robustness, run every session file in examples/ through the pipeline and verify no exceptions:

```python
import glob

def test_all_sessions_no_crash():
    """Every real session file processes without crashing."""
    session_files = glob.glob("examples/projects/**/*.jsonl", recursive=True)
    assert len(session_files) > 0, "No session files found"

    for path in session_files:
        # Should not raise any exception
        lines = read_session(path)
        state = ScreenState()
        for line in lines:
            render(state, line)
        # Just verify it produces some output (even if empty for metadata-only sessions)
        state.to_markdown()
```

### 5. Specific Scenario Tests

Create focused integration tests for specific protocol flows:

**Test: User → Thinking → Text → Turn Duration**
```python
def test_full_turn_flow():
    lines = [
        {"type": "file-history-snapshot", ...},  # invisible
        {"type": "user", "isMeta": False, "message": {"role": "user", "content": "hello"}},
        {"type": "assistant", "requestId": "req_1", "message": {"content": [{"type": "thinking", "thinking": "..."}]}},
        {"type": "assistant", "requestId": "req_1", "message": {"content": [{"type": "text", "text": "Hi there!"}]}},
        {"type": "system", "subtype": "turn_duration", "durationMs": 5000},
    ]
    state = ScreenState()
    for line in lines:
        render(state, line)
    md = state.to_markdown()
    assert "❯ hello" in md
    assert "✱ Thinking…" in md
    assert "● Hi there!" in md
    assert "✱ Crunched for 5s" in md
```

**Test: Tool Call → Progress → Result**
```python
def test_tool_with_progress():
    # ... tool_use, bash_progress, tool_result sequence
    # Verify final output shows result, not progress
```

**Test: Compaction Mid-Session**
```python
def test_compaction_clears_history():
    # Build up 3 messages, then compact, then 2 more
    # Verify output only has the 2 post-compaction messages
```

**Test: Parallel Tool Calls**
```python
def test_parallel_tools():
    # Two tool_use with same requestId, two results
    # Verify both rendered, both matched correctly
```

### 6. CLI Entry Point (Optional)

If not already done, implement a basic CLI in `cli.py`:

```python
#!/usr/bin/env python3
"""Replay a Claude Code session as ASCII terminal output."""
import sys
import json
from pathlib import Path
from claude_session_player.parser import read_session
from claude_session_player.renderer import render
from claude_session_player.models import ScreenState

def main():
    if len(sys.argv) != 2:
        print("Usage: claude-session-player <session.jsonl>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    lines = read_session(path)
    state = ScreenState()
    for line in lines:
        render(state, line)
    print(state.to_markdown())

if __name__ == "__main__":
    main()
```

Add to `pyproject.toml`:
```toml
[project.scripts]
claude-session-player = "claude_session_player.cli:main"
```

### 7. Coverage Report

Run `pytest --cov=claude_session_player` and document coverage. Target: ≥85% line coverage.

## Test Requirements

### Snapshot Tests:
- ≥5 real sessions with snapshot comparison
- Each snapshot manually verified for correctness

### No-Crash Tests:
- Every `.jsonl` file in examples/ processes without exception
- Subagent files also processed without exception

### Scenario Tests:
- Full turn lifecycle
- Tool call with progress and result
- Compaction mid-session
- Parallel tool calls
- Sub-agent collapsed result
- Multiple user messages across turns
- Session with only metadata (no visible content)

### CLI:
- `python -m claude_session_player.cli <file>` produces output
- Missing file argument → usage message

## Definition of Done

- [ ] `replay_session()` helper function for integration tests
- [ ] ≥5 snapshot tests with real session data
- [ ] No-crash test covers all example files
- [ ] ≥6 focused scenario integration tests
- [ ] CLI entry point works
- [ ] All tests pass (unit + integration)
- [ ] Coverage ≥85%
- [ ] Total test count across all issues: ≥100

## Worklog

Write `issues/worklogs/10-worklog.md` with:
- Sessions selected for snapshots and why
- Coverage report
- Total test count
- Any bugs found and fixed during integration testing
- Any protocol spec updates needed
- Final project summary: what works, what's missing, what could be improved
