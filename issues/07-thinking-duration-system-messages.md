# Issue 07: Thinking, Turn Duration & System Messages

## Priority: P1 — Important
## Dependencies: Issues 01, 02
## Estimated Complexity: Low

## Summary

Implement rendering of thinking indicators, turn duration timing lines, and handle system message types (compact_boundary, local_command).

## Context

Before starting, read:
- `issues/worklogs/01-worklog.md` through `issues/worklogs/06-worklog.md`

Three assistant/system message types need handling:
1. **Thinking blocks**: Show `✱ Thinking…` (fixed text, raw thinking not displayed)
2. **Turn duration**: Show `✱ Crunched for Xm Ys` with formatted time
3. **Compact boundary**: Clear all state (conversation restart after compaction)

### Key Spec References
- `.claude/specs/claude-session-player.md` — thinking, turn_duration, compact_boundary rows

### Real Data

**Thinking block:**
```json
{"type":"assistant","requestId":"req_001","message":{"content":[{"type":"thinking","thinking":"The user wants to clean up...","signature":"Eu4ECk..."}],"stop_reason":null}}
```

**Turn duration:**
```json
{"type":"system","subtype":"turn_duration","durationMs":88947}
```
→ 88947ms = 1m 28s → `✱ Crunched for 1m 28s`

**Compact boundary:**
```json
{"type":"system","subtype":"compact_boundary","content":"Conversation compacted","compactMetadata":{"trigger":"auto","preTokens":155025}}
```

## Detailed Requirements

### 1. Render THINKING

When `classify_line` returns `THINKING`:
1. Get `request_id` from line
2. Create `ThinkingIndicator()` with `request_id` set
3. Append to `state.elements`
4. Update `state.current_request_id = request_id`

Add `request_id` field to `ThinkingIndicator`:
```python
@dataclass
class ThinkingIndicator:
    request_id: str | None = None
```

Format: `✱ Thinking…`

### 2. Render TURN_DURATION

When `classify_line` returns `TURN_DURATION`:
1. Extract `duration_ms` via `get_duration_ms(line)`
2. Create `TurnDuration(duration_ms=duration_ms)`
3. Append to `state.elements`
4. Reset `state.current_request_id = None`

### 3. Duration Formatting

```python
def format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration."""
    total_seconds = ms // 1000
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}m {seconds}s"
```

Format in markdown: `✱ Crunched for {format_duration(duration_ms)}`

### 4. Render COMPACT_BOUNDARY

When `classify_line` returns `COMPACT_BOUNDARY`:
1. Call `state.clear()` — clears all elements, tool_calls, resets current_request_id
2. This effectively "restarts" the screen — only post-compaction messages will appear

### 5. Handle INVISIBLE System Messages

`local_command` system messages → `INVISIBLE` → no action (already handled by classify returning INVISIBLE).

### 6. Add render() Dispatches

```python
case LineType.THINKING:
    _render_thinking(state, line)
case LineType.TURN_DURATION:
    _render_turn_duration(state, line)
case LineType.COMPACT_BOUNDARY:
    _render_compact_boundary(state, line)
```

### 7. Update format_element

```python
case ThinkingIndicator():
    return "✱ Thinking…"
case TurnDuration(duration_ms=ms):
    return f"✱ Crunched for {format_duration(ms)}"
```

## Test Requirements

### Thinking:
- Thinking block → `✱ Thinking…` in markdown (raw text NOT shown)
- Thinking block groups with text block via same requestId
- Thinking → text sequence with same requestId → no blank line between

### Turn Duration:
- 5000ms → `✱ Crunched for 5s`
- 65000ms → `✱ Crunched for 1m 5s`
- 120000ms → `✱ Crunched for 2m 0s`
- 0ms → `✱ Crunched for 0s`
- 59999ms → `✱ Crunched for 59s`
- 88947ms → `✱ Crunched for 1m 28s`

### Compact Boundary:
- State with elements → compact_boundary → state.elements is empty
- State with tool_calls → compact_boundary → state.tool_calls is empty
- State with current_request_id → compact_boundary → reset to None
- Messages after compact_boundary rendered normally

### Full Flow:
- User → thinking → text (same requestId) → `❯ msg\n✱ Thinking…\n● response`
- User → assistant → turn_duration → `❯ msg\n● response\n\n✱ Crunched for Xs`
- Build state → compact_boundary → user → only user message in output

## Definition of Done

- [ ] Thinking renders as `✱ Thinking…` (fixed text)
- [ ] ThinkingIndicator has `request_id` for grouping
- [ ] Turn duration formatted correctly for all ranges
- [ ] Compact boundary clears state completely
- [ ] All format_element cases implemented
- [ ] ≥12 unit tests, all passing
- [ ] All prior tests still pass

## Worklog

Write `issues/worklogs/07-worklog.md` with:
- Duration formatting edge cases
- Test count and results
- Any model changes needed
