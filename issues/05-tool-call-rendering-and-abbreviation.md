# Issue 05: Tool Call Rendering & Abbreviation

## Priority: P0 — Core
## Dependencies: Issues 01, 02, 04
## Estimated Complexity: Medium

## Summary

Implement rendering of `tool_use` assistant blocks — the `● Bash(command…)` lines. This includes the tool-specific input abbreviation logic and registering tool calls in state for later result matching.

## Context

Before starting, read:
- `issues/worklogs/01-worklog.md` through `issues/worklogs/04-worklog.md`

When the assistant calls a tool, it emits a `tool_use` content block. The renderer displays this as a compact one-liner showing the tool name and an abbreviated version of its input. The tool call must be registered in `state.tool_calls` so that when the result arrives later, it can be matched back and displayed underneath.

### Key Spec References
- `.claude/specs/claude-session-player.md` — "Tool Input Abbreviation" table, "Tool Result Matching"
- `claude-code-session-protocol-schema.md` — section 7 "Tool Use Protocol", Appendix B "Known Tool Names"

### Real Data Examples

**Bash with description:**
```json
{"type":"tool_use","id":"toolu_011KE171EW6bVUT2iv2aBzx7","name":"Bash","input":{"command":"rm -rf frontend/node_modules","description":"Remove node_modules and frontend build artifacts"}}
```
→ Renders as: `● Bash(Remove node_modules and frontend build artifacts)`

**Read:**
```json
{"type":"tool_use","id":"toolu_001","name":"Read","input":{"file_path":"/Users/agutnikov/work/project/README.md"}}
```
→ Renders as: `● Read(README.md)`

**Bash without description:**
```json
{"type":"tool_use","id":"toolu_002","name":"Bash","input":{"command":"git status && git diff HEAD"}}
```
→ Renders as: `● Bash(git status && git diff HEAD)`

## Detailed Requirements

### 1. Tool Input Abbreviation (`tools.py`)

```python
def abbreviate_tool_input(tool_name: str, input_dict: dict) -> str:
    """Return abbreviated display label for a tool call."""
```

Abbreviation rules by tool name:

| Tool | Primary Field | Fallback | Transform |
|---|---|---|---|
| `Bash` | `input.description` | `input.command` | First 60 chars |
| `Read` | `input.file_path` | — | Basename only (e.g., `/a/b/c.py` → `c.py`) |
| `Write` | `input.file_path` | — | Basename only |
| `Edit` | `input.file_path` | — | Basename only |
| `Glob` | `input.pattern` | — | First 60 chars |
| `Grep` | `input.pattern` | — | First 60 chars |
| `Task` | `input.description` | — | First 60 chars |
| `WebSearch` | `input.query` | — | First 60 chars |
| `WebFetch` | `input.url` | — | First 60 chars |
| `NotebookEdit` | `input.notebook_path` | — | Basename only |
| `TodoWrite` | — | — | Fixed: `todos` |
| Unknown | — | — | `…` |

Truncation: if text exceeds 60 chars, truncate and append `…`.

```python
def _truncate(text: str, max_len: int = 60) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"

def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1] if "/" in path else path
```

### 2. Render TOOL_USE

When `classify_line` returns `TOOL_USE`:

1. Extract `(tool_name, tool_use_id, input_dict)` via `get_tool_use_info(line)`
2. Compute label: `abbreviate_tool_input(tool_name, input_dict)`
3. Get `request_id` from line
4. Create `ToolCall(tool_name=tool_name, tool_use_id=tool_use_id, label=label)`
5. Set `tool_call.request_id = request_id` (for response grouping)
6. Append to `state.elements`
7. Register: `state.tool_calls[tool_use_id] = len(state.elements) - 1`
8. Update `state.current_request_id = request_id`

### 3. Update ToolCall Model

Add `request_id` field to `ToolCall`:
```python
@dataclass
class ToolCall:
    tool_name: str
    tool_use_id: str
    label: str
    result: str | None = None
    is_error: bool = False
    progress_text: str | None = None
    request_id: str | None = None
```

### 4. Update to_markdown() for ToolCall

```python
case ToolCall():
    line = f"● {element.tool_name}({element.label})"
    if element.progress_text is not None:
        line += f"\n  └ {element.progress_text}"
    if element.result is not None:
        prefix = "  ✗ " if element.is_error else "  └ "
        line += f"\n{prefix}{element.result}"
    return line
```

Note: result and progress rendering is actually done in issues 06 and 08, but the format_element for ToolCall should handle these fields if they're set.

### 5. Parallel Tool Calls

Multiple `tool_use` blocks with the same `requestId`:
- Each gets its own `● ToolName(...)` line
- Each registered separately in `state.tool_calls`
- All share the same `request_id` for grouping (no blank line between them)
- Order: JSONL file order (which is the order they appear)

### 6. Add render() Dispatch

```python
case LineType.TOOL_USE:
    _render_tool_use(state, line)
```

## Test Requirements

### Abbreviation Tests (`test_tools.py`):
- Bash with description → uses description
- Bash without description → uses command
- Bash with long command → truncated at 60 chars with `…`
- Read with full path → basename only
- Read with basename only → unchanged
- Write, Edit → basename
- Glob, Grep → pattern, truncated if needed
- Task → description, truncated if needed
- WebSearch → query
- WebFetch → url
- Unknown tool → `…`
- Empty input dict → reasonable fallback (tool name only)
- Missing expected field → graceful fallback

### Rendering Tests (`test_renderer.py`):
- Single tool_use → `● Bash(label)` in markdown
- Tool call registered in `state.tool_calls` with correct index
- Two parallel tool_uses with same requestId → no blank line between them
- Tool_use after text block with same requestId → no blank line
- Tool_use with new requestId → blank line separator
- `current_request_id` updated after tool_use

### Markdown Output:
- User message → tool call → correct spacing
- Tool call without result → just the `● ToolName(label)` line
- Tool call with result already set → includes `└` line (preview of issue 06)

## Definition of Done

- [ ] `abbreviate_tool_input()` handles all 10+ known tools correctly
- [ ] Truncation at 60 chars with `…` works
- [ ] Basename extraction works for full paths and bare filenames
- [ ] `_render_tool_use()` creates `ToolCall` elements
- [ ] Tool calls registered in `state.tool_calls` dict
- [ ] `request_id` grouping works for parallel tool calls
- [ ] `format_element` for `ToolCall` produces correct markdown
- [ ] ≥20 unit tests (abbreviation + rendering), all passing
- [ ] All prior tests still pass

## Worklog

Write `issues/worklogs/05-worklog.md` with:
- Tool abbreviation decisions for edge cases
- Any new tools discovered in real data not in the spec
- Test count and results
