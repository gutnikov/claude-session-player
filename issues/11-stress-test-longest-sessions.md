# Issue 11: Stress Test — Replay Longest Sessions & Fix Breakage

## Priority: P0 — Validation
## Dependencies: All prior issues (01–10)
## Estimated Complexity: High

## Summary

Find the longest/most complex real JSONL session files from `examples/`, replay them through the full renderer pipeline, analyze every line of output for correctness, and fix any bugs or rendering issues discovered.

## Context

Before starting, read:
- ALL worklogs: `issues/worklogs/01-worklog.md` through `issues/worklogs/10-worklog.md`
- The spec: `.claude/specs/claude-session-player.md`
- The protocol: `claude-code-session-protocol-schema.md`

Issues 01–10 built the renderer with unit tests and basic integration tests. This issue is the real-world validation pass: take the biggest, most complex sessions and see what breaks. These sessions exercise protocol features in combinations that synthetic tests don't cover.

## Detailed Requirements

### 1. Find the Longest Sessions

Scan all JSONL files in `examples/projects/` and identify the top 5 by line count. These are the most complex sessions with the most protocol features exercised.

```bash
find examples/projects -name "*.jsonl" -not -path "*/subagents/*" \
  | xargs wc -l | sort -rn | head -20
```

Also find the top 3 subagent files:
```bash
find examples/projects -path "*/subagents/*.jsonl" \
  | xargs wc -l | sort -rn | head -10
```

### 2. Sequential Replay & Analysis

For each of the top 5 main sessions:

1. **Replay**: Run through `render()` for every line
2. **Capture output**: Save `state.to_markdown()` to a file
3. **Analyze output manually**: Read the markdown output line by line and check:
   - Are user messages rendered with `❯` prefix?
   - Are assistant text blocks rendered with `●` prefix?
   - Are tool calls showing correct abbreviations?
   - Are tool results matched to the right tool calls?
   - Are thinking indicators showing `✱ Thinking…`?
   - Are turn durations formatted correctly?
   - Is spacing correct (blank lines between elements, no blank lines within same requestId)?
   - Did compaction clear state correctly (if session has compaction)?
   - Are sub-agent results collapsed?
   - Are progress messages updating the right tool calls?
   - Are there any unexpected blank elements, missing text, or garbled output?
   - Are local command outputs rendered?

4. **Document each issue found**: For every bug or rendering problem:
   - Which session file
   - Which line number in the JSONL
   - What the line contains (message type, content summary)
   - What the renderer produced
   - What it should have produced
   - Root cause analysis

5. **Fix the bug**: Implement the fix in the appropriate module
6. **Add a regression test**: Write a test that reproduces the exact bug with the specific input that caused it
7. **Re-run replay**: Verify the fix and check for new issues

### 3. Common Issues to Watch For

Based on the protocol research, these are likely trouble spots:

**a) Multiple content blocks in tool results**
Some tool results have `content` as a list of blocks, not a string. The renderer may crash or produce empty output.

**b) Very long tool outputs**
Real Bash outputs can be thousands of lines. Truncation to 5 lines must work correctly.

**c) Rapid parallel tool calls**
Sessions with 5+ parallel tool calls — verify all are registered in `state.tool_calls` and all results match back.

**d) Compaction mid-tool-flow**
A tool call happens before compaction, its result arrives after. The orphan result handling must work.

**e) Progress messages without matching tool**
Some progress messages (especially `hook_progress` for `SessionStart`) have no corresponding tool call. Must not crash.

**f) Empty or null fields**
Real data sometimes has `null` for optional fields like `gitBranch`, `slug`, `permissionMode`. Must not crash.

**g) Mixed requestId patterns**
Some sessions show thinking → text → tool_use → tool_use all in one requestId. Verify grouping logic handles this sequence.

**h) Unicode and special characters**
Real user messages and tool outputs contain emoji, non-ASCII, markdown special chars. Verify passthrough works.

**i) Very long single lines**
Some assistant text blocks are paragraphs with no line breaks. Verify they render without issues.

**j) Deeply nested tool flows**
Tool call → result → tool call → result → tool call → result (many rounds). Verify state doesn't grow unboundedly or lose track.

### 4. Also Replay Top 3 Subagent Files

Subagent files are standalone conversations that start with `parentUuid: null` and have `isSidechain: true` on every message. The renderer should handle them — they're just like main sessions but with the sidechain flag.

Verify:
- Subagent sessions replay without crashes
- The sidechain flag doesn't cause issues (it shouldn't — main session filtering of sidechain messages is for when they appear IN main session files)

### 5. Performance Check

For the longest session:
- Time the full replay: `time python -c "from claude_session_player.parser import read_session; from claude_session_player.renderer import render; from claude_session_player.models import ScreenState; lines = read_session('path'); state = ScreenState(); [render(state, l) for l in lines]; state.to_markdown()"`
- Should complete in under 5 seconds for any session
- If slow, profile and optimize the hot path

### 6. Save Validated Outputs as Snapshots

After fixing all issues, save the final replay outputs as reference snapshots:
```
tests/snapshots/stress_session_1.md
tests/snapshots/stress_session_2.md
...
tests/snapshots/stress_session_5.md
```

Add snapshot comparison tests in `tests/test_stress.py`:
```python
import pytest
from claude_session_player.parser import read_session
from claude_session_player.renderer import render
from claude_session_player.models import ScreenState

STRESS_SESSIONS = [
    ("examples/projects/.../session1.jsonl", "tests/snapshots/stress_session_1.md"),
    # ... etc
]

@pytest.mark.parametrize("jsonl_path,snapshot_path", STRESS_SESSIONS)
def test_stress_session(jsonl_path, snapshot_path):
    lines = read_session(jsonl_path)
    state = ScreenState()
    for line in lines:
        render(state, line)
    output = state.to_markdown()

    with open(snapshot_path) as f:
        expected = f.read()

    assert output == expected
```

### 7. Write Comprehensive Worklog

The worklog for this issue is the most important one. It serves as the final project report.

## Test Requirements

- ≥5 regression tests (one per bug found and fixed)
- ≥5 stress session snapshot tests
- ≥3 subagent replay tests
- 1 performance test (longest session completes in <5s)
- All prior tests still pass
- Final test count: document total across all issues

## Definition of Done

- [ ] Top 5 longest main sessions identified and replayed
- [ ] Top 3 subagent files replayed
- [ ] Every line of output analyzed for correctness
- [ ] All bugs found, documented, fixed, and regression-tested
- [ ] Stress session snapshots saved
- [ ] Snapshot comparison tests pass
- [ ] Performance: longest session replays in <5s
- [ ] All tests pass (full suite)
- [ ] Comprehensive worklog written

## Worklog

Write `issues/worklogs/11-worklog.md` with:

### Bug Report Table
| # | Session | JSONL Line | Message Type | Issue | Root Cause | Fix |
|---|---|---|---|---|---|---|
| 1 | ... | ... | ... | ... | ... | ... |

### Sessions Tested
- Session path, line count, features exercised, issues found

### Performance Results
- Session path, line count, replay time

### Final Project Status
- Total tests across all issues
- Coverage percentage
- Known limitations
- Potential future improvements
- Protocol spec corrections needed (if any)
