# Claude Session Player — Final Spec

## Overview

A Python tool that takes Claude Code JSONL session history files and replays them as ASCII terminal output in markdown format. Each JSONL line acts as a "frame update" that changes the visible screen state. The tool uses a stateful render function to process lines one at a time.

## Goals

- Process Claude Code session JSONL lines one at a time via a stateful render function
- Render ASCII terminal content as markdown text
- Provide a render function: `render(state, line) → state`

## API Design

```python
def render(state: ScreenState, line: dict) -> ScreenState
```

- Takes the previous screen state and the next parsed JSONL line
- Returns the updated (mutated) screen state
- `ScreenState` is **mutable** — the same object is mutated and returned
- `ScreenState` exposes a `.to_markdown() -> str` method for the final ASCII output
- Initial state: `ScreenState()` (empty screen)
- The render function dispatches based on `line["type"]` and relevant subtypes

## Input

- `state`: Previous `ScreenState` (or empty initial state)
- `line`: A single parsed JSONL line (dict) following the Claude Code Session Protocol (v2.0.76 – v2.1.29)

## Output

- Updated `ScreenState` object (same instance, mutated)
- `.to_markdown()` returns the full terminal screen as markdown text

## Message Types & Visibility

| Message Type | Visible | Rendering |
|---|---|---|
| `user` (direct input, `isMeta=false`, content is string) | Yes | `❯` prompt prefix; first line `❯ text`, subsequent lines indented 2 spaces |
| `user` (skill expansion, `isMeta=true`) | No | Invisible |
| `user` (tool result, content has `tool_result` blocks) | Yes | Updates corresponding tool call widget with `└` connector; errors use `✗` |
| `user` (local command stdout, content has `<local-command-stdout>`) | Yes | Rendered as system output line |
| `user` (local command caveat, `isMeta=true`) | No | Invisible |
| `assistant` (text block) | Yes | `● ` prefix on first line, 2-space indent on continuation; markdown verbatim |
| `assistant` (tool_use block) | Yes | `● ToolName(abbreviated_input…)` |
| `assistant` (thinking block) | Yes | `✱ Thinking…` (fixed text, raw thinking NOT shown) |
| `system` (turn_duration) | Yes | `✱ Crunched for Xm Xs` |
| `system` (compact_boundary) | Special | Clears all pre-compaction content from state |
| `system` (local_command) | No | Invisible |
| `summary` | No | Invisible |
| `progress` (bash_progress) | Yes | Updates `└` line under corresponding tool call (matched via `parentToolUseID`) |
| `progress` (agent_progress) | Yes | `  └ Agent: working…` under Task tool call |
| `progress` (hook_progress) | Yes | `  └ Hook: {hookName}` under corresponding tool call |
| `progress` (query_update) | Yes | `  └ Searching: {query}` under WebSearch tool call |
| `progress` (search_results_received) | Yes | `  └ {resultCount} results` under WebSearch tool call |
| `progress` (waiting_for_task) | Yes | `  └ Waiting: {taskDescription}` |
| `file-history-snapshot` | No | Invisible |
| `queue-operation` | No | Invisible |
| `pr-link` | No | Invisible |

## Tool Input Abbreviation

| Tool | Displayed Field | Fallback | Example |
|---|---|---|---|
| `Bash` | `description` (first 60 chars) | `command` (first 60 chars) | `● Bash(Remove node_modules and build artifacts)` |
| `Read` | `file_path` (basename only) | — | `● Read(README.md)` |
| `Write` | `file_path` (basename only) | — | `● Write(.gitignore)` |
| `Edit` | `file_path` (basename only) | — | `● Edit(config.py)` |
| `Glob` | `pattern` (first 60 chars) | — | `● Glob(**/*.ts)` |
| `Grep` | `pattern` (first 60 chars) | — | `● Grep(TODO)` |
| `Task` | `description` (first 60 chars) | — | `● Task(Explore codebase structure…)` |
| `WebSearch` | `query` (first 60 chars) | — | `● WebSearch(Claude hooks 2026…)` |
| `WebFetch` | `url` (first 60 chars) | — | `● WebFetch(https://example.com…)` |
| Other | tool name only | — | `● UnknownTool(…)` |

When a field exceeds 60 chars, truncate and append `…`.

## Key Rendering Behaviors

### Content Block Merging
- Assistant content blocks sharing the same `requestId` belong to the same response
- They are rendered sequentially with no extra blank line between them
- Each block type renders according to its own rules (text → `●`, tool_use → `● Tool(...)`, thinking → `✱`)

### Tool Result Matching
- Tool results are `user` messages with `tool_result` content blocks
- Match via `content[].tool_use_id` ↔ `tool_use.id` stored in state
- Additionally, `sourceToolAssistantUUID` on the tool result message links to the assistant message UUID

### Progress Message Matching
- Progress messages link to tool calls via `parentToolUseID` field
- `parentToolUseID` matches the original `tool_use.id`
- The progress message's own `toolUseID` is auto-generated (e.g., `"bash-progress-0"`)

### Tool Result Rendering
- Success: `  └ {output text}` (indented 2 spaces)
- Error (`is_error: true`): `  ✗ {error text}` (indented 2 spaces)
- Output truncated to 5 lines; if truncated, last line is `  └ …`

### Parallel Tool Calls
- Multiple `tool_use` blocks with same `requestId` appear as separate JSONL lines
- Rendered vertically in JSONL order, each with own `● ToolName(...)` line
- Results matched back individually via `tool_use_id`

### Sub-Agent Rendering (Collapsed)
- Tool call: `● Task(description…)`
- Result: `  └ {first 80 chars of toolUseResult.content[0].text}`

### Context Compaction
- When `compact_boundary` is encountered, clear all content from state
- Only post-compaction messages are rendered
- `summary` messages are invisible (not rendered)

### Turn Duration
- `system` with `subtype: "turn_duration"` and `durationMs` field
- Rendered as `✱ Crunched for {formatted_duration}`
- Format: `Xm Ys` for >= 60s, `Xs` for < 60s

### Local Command Output
- User messages with `<local-command-stdout>...</local-command-stdout>` content
- Extract text between tags and render as a plain output line

## Formatting Rules

- Terminal width: 80 columns
- Lines exceeding 80 chars: no wrapping (markdown output, let viewer handle it)
- Tool outputs: truncated to 5 lines max
- Tool input labels: truncated at 60 chars with `…`
- One blank line between each top-level element (user message, assistant response block, timing line)
- No blank line between content blocks within the same `requestId` group
- Markdown in assistant text blocks: passed through verbatim (output IS markdown)

## ScreenState Internal Structure

```python
class ScreenState:
    elements: list[ScreenElement]       # Ordered list of rendered elements
    tool_calls: dict[str, int]          # tool_use_id → index in elements (for result/progress updates)
    current_request_id: str | None      # Track current assistant response group
```

`ScreenElement` is a tagged union / dataclass representing one visual block:
- `UserMessage(text: str)`
- `AssistantText(text: str)`
- `ToolCall(tool_name: str, label: str, result: str | None, is_error: bool)`
- `ThinkingIndicator()`
- `TurnDuration(duration_ms: int)`
- `SystemOutput(text: str)`

## Detecting Message Subtypes

### User message classification:
1. If `isMeta is True` → invisible
2. If `message.content` is a string:
   - If contains `<local-command-stdout>` → local command output
   - If contains `<local-command-caveat>` → invisible (redundant with isMeta check)
   - Otherwise → direct user input
3. If `message.content` is a list:
   - If any block has `type: "tool_result"` → tool result
   - Otherwise → direct user input (content blocks as text)

### Assistant message classification:
- Check `message.content[0].type`: `"text"`, `"tool_use"`, or `"thinking"`

### System message classification:
- Check `subtype`: `"turn_duration"`, `"compact_boundary"`, `"local_command"`

### Progress message classification:
- Check `data.type`: `"bash_progress"`, `"hook_progress"`, `"agent_progress"`, `"query_update"`, `"search_results_received"`, `"waiting_for_task"`

## Testing Approach

- Unit tests comparing `.to_markdown()` output against expected markdown strings
- Test each message type independently with hand-crafted JSONL dicts
- Test state mutation: verify render returns the same object
- Test tool result matching: create tool_use, then tool_result, verify output
- Test progress updates: create tool_use, then progress, verify `└` line updates
- Test compaction: build state, send compact_boundary, verify state cleared
- Test parallel tools: multiple tool_use with same requestId
- Integration tests: fold over real JSONL files from `examples/` directory

## Project Structure

```
claude_session_player/
├── __init__.py
├── models.py          # ScreenState, ScreenElement dataclasses
├── renderer.py        # render() function, dispatch logic
├── formatter.py       # to_markdown() and formatting helpers
├── parser.py          # JSONL reading, line validation
├── tools.py           # Tool-specific abbreviation/rendering
└── cli.py             # Optional CLI entry point

tests/
├── __init__.py
├── test_renderer.py   # Unit tests per message type
├── test_formatter.py  # Markdown output tests
├── test_tools.py      # Tool abbreviation tests
├── test_parser.py     # JSONL parsing tests
├── test_integration.py # Full session replay tests
└── fixtures/          # Hand-crafted JSONL test data
```
