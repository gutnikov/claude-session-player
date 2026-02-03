# Claude Session Player

A Python tool that replays Claude Code JSONL session history files as readable ASCII terminal output in markdown format.

## What It Does

Claude Code stores conversation history in JSONL (JSON Lines) files. Each line represents a "frame update" — a user message, assistant response, tool invocation, or progress update. Claude Session Player processes these session files and renders them as human-readable markdown, showing:

- User prompts (❯)
- Assistant responses (●)
- Thinking indicators (✱)
- Tool calls with their inputs and results
- Progress updates for long-running commands
- Turn duration timing

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/your-org/claude-session-player.git
cd claude-session-player

# Install in development mode
pip install -e .

# Or install with dev dependencies for testing
pip install -e ".[dev]"
```

### Requirements

- Python 3.12+
- No runtime dependencies (stdlib only)
- Dev dependencies: pytest, pytest-cov

## Quick Start

### Command Line

```bash
# Replay a session file
claude-session-player path/to/session.jsonl

# Or run as a Python module
python -m claude_session_player.cli path/to/session.jsonl
```

### As a Library

```python
from claude_session_player.models import ScreenState
from claude_session_player.parser import read_session
from claude_session_player.renderer import render

# Load and replay a session
lines = read_session("path/to/session.jsonl")
state = ScreenState()

for line in lines:
    render(state, line)

# Get the markdown output
markdown = state.to_markdown()
print(markdown)
```

## Finding Your Session Files

Claude Code stores session files in:

- **macOS**: `~/.claude/projects/<project-hash>/sessions/*.jsonl`
- **Linux**: `~/.claude/projects/<project-hash>/sessions/*.jsonl`
- **Windows**: `%USERPROFILE%\.claude\projects\<project-hash>\sessions\*.jsonl`

Each project has a unique hash based on its path. Sessions are named with UUIDs like `a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl`.

## Output Format

### User Messages

User input is prefixed with `❯`:

```
❯ Hello, can you help me with this code?
```

Multi-line input:

```
❯ Here's my code:
  def foo():
      return 42
```

### Assistant Responses

Assistant text is prefixed with `●`:

```
● I'd be happy to help! Let me take a look at your code.
```

Multi-line responses maintain the indent:

```
● Here's how it works:
  1. First, we initialize the state
  2. Then we process each line
  3. Finally, we render the output
```

### Thinking Indicators

When Claude is thinking (extended thinking mode), a thinking indicator appears:

```
✱ Thinking…
```

The raw thinking content is not displayed — just the indicator.

### Tool Calls

Tool invocations show the tool name and abbreviated input:

```
● Read(config.py)
● Bash(Run the test suite)
● Grep(TODO)
● Task(Explore codebase structure)
```

Tool inputs are abbreviated to 60 characters. Different tools show different fields:

| Tool | Display Field | Example |
|------|--------------|---------|
| Bash | `description` or `command` | `Bash(Install dependencies)` |
| Read/Write/Edit | `file_path` (basename) | `Read(config.py)` |
| Glob/Grep | `pattern` | `Glob(**/*.ts)` |
| Task | `description` | `Task(Research the API…)` |
| WebSearch | `query` | `WebSearch(Python asyncio tutorial)` |
| WebFetch | `url` | `WebFetch(https://docs.python.org…)` |

### Tool Results

Successful results appear with `└`:

```
● Bash(git status)
  └ On branch main
    Your branch is up to date with 'origin/main'.
```

Errors appear with `✗`:

```
● Read(nonexistent.py)
  ✗ Error: File not found
```

Long outputs are truncated to 5 lines:

```
● Bash(find . -name "*.py")
  └ ./src/main.py
    ./src/utils.py
    ./src/models.py
    ./tests/test_main.py
    …
```

### Progress Updates

Long-running commands show progress updates:

```
● Bash(npm install)
  └ added 1432 packages in 45s
```

Task agent progress:

```
● Task(Analyze codebase)
  └ Agent: working…
```

Web search progress:

```
● WebSearch(Python best practices 2024)
  └ Searching: Python best practices 2024
```

### Turn Duration

After each assistant turn, the processing time is shown:

```
✱ Crunched for 1m 28s
```

Or for shorter turns:

```
✱ Crunched for 5s
```

## Complete Example

Here's a complete example showing various message types:

```
❯ Can you help me clean up my project directory?

✱ Thinking…
● I'll help you clean up the project. Let me remove common build artifacts
  and cache directories.
● Bash(Remove node_modules and build artifacts)
  └ Removed node_modules/
    Removed dist/
    Removed .cache/
● Bash(Remove Python cache files)
  └ Removed __pycache__/
    Removed .pytest_cache/

✱ Thinking…
● Done! I've cleaned up:
  - `node_modules/`, `dist/`, `.cache/` from the frontend
  - `__pycache__/`, `.pytest_cache/` from Python

  Your directory is now ready to package.

✱ Crunched for 12s
```

## API Reference

### Core Functions

#### `render(state: ScreenState, line: dict) -> ScreenState`

Process a single JSONL line and update the screen state.

```python
from claude_session_player.models import ScreenState
from claude_session_player.renderer import render

state = ScreenState()
line = {"type": "user", "message": {"content": "Hello"}}
state = render(state, line)
```

**Arguments:**
- `state`: The current `ScreenState` (mutated in place)
- `line`: A parsed JSONL line dictionary

**Returns:** The same `state` object, updated.

#### `read_session(path: str) -> list[dict]`

Read and parse all lines from a JSONL session file.

```python
from claude_session_player.parser import read_session

lines = read_session("session.jsonl")
for line in lines:
    print(line.get("type"))
```

#### `classify_line(line: dict) -> LineType`

Classify a JSONL line into one of 15 line types.

```python
from claude_session_player.parser import classify_line, LineType

line_type = classify_line({"type": "user", "message": {"content": "hi"}})
assert line_type == LineType.USER_INPUT
```

### Data Models

#### `ScreenState`

Mutable state representing the terminal screen.

```python
from claude_session_player.models import ScreenState

state = ScreenState()
state.elements      # list[ScreenElement] - rendered elements
state.tool_calls    # dict[str, int] - tool_use_id → element index
state.current_request_id  # str | None - current response group

# Get markdown output
markdown = state.to_markdown()

# Clear all state (used on compaction)
state.clear()
```

#### Screen Elements

All visual elements that can appear in the output:

```python
from claude_session_player.models import (
    UserMessage,      # User input (❯)
    AssistantText,    # Assistant response (●)
    ToolCall,         # Tool invocation (● ToolName(...))
    ThinkingIndicator,  # Thinking (✱ Thinking…)
    TurnDuration,     # Timing (✱ Crunched for...)
    SystemOutput,     # System/local command output
)
```

#### LineType Enum

Classification of JSONL line types:

```python
from claude_session_player.parser import LineType

# User message types
LineType.USER_INPUT           # Direct user text
LineType.TOOL_RESULT          # Tool result content
LineType.LOCAL_COMMAND_OUTPUT # <local-command-stdout>

# Assistant message types
LineType.ASSISTANT_TEXT       # Text response
LineType.TOOL_USE            # Tool invocation
LineType.THINKING            # Thinking block

# System message types
LineType.TURN_DURATION       # Turn timing
LineType.COMPACT_BOUNDARY    # Context compaction marker

# Progress message types
LineType.BASH_PROGRESS       # Bash command output
LineType.HOOK_PROGRESS       # Hook execution
LineType.AGENT_PROGRESS      # Sub-agent progress
LineType.QUERY_UPDATE        # Search query
LineType.SEARCH_RESULTS      # Search results count
LineType.WAITING_FOR_TASK    # Waiting for task

# Skip type
LineType.INVISIBLE           # Metadata, should not render
```

## Advanced Usage

### Processing Large Sessions

For very large sessions, process incrementally:

```python
import json
from claude_session_player.models import ScreenState
from claude_session_player.renderer import render

state = ScreenState()
with open("large_session.jsonl") as f:
    for line_text in f:
        if line_text.strip():
            line = json.loads(line_text)
            render(state, line)

print(state.to_markdown())
```

### Handling Context Compaction

Claude Code uses "context compaction" to manage long conversations. When a `compact_boundary` is encountered, all prior content is cleared from the state:

```python
# After compaction, only post-compaction content is visible
state = ScreenState()
render(state, user_message_1)    # Will be cleared
render(state, assistant_reply_1) # Will be cleared
render(state, compact_boundary)  # Clears all state
render(state, user_message_2)    # Visible in output
render(state, assistant_reply_2) # Visible in output
```

### Sub-Agent Sessions

Task tool invocations spawn sub-agents. Their internal messages have `isSidechain=True` and are rendered as `INVISIBLE`. The Task result shows a collapsed summary:

```
● Task(Analyze authentication system)
  └ The codebase uses JWT tokens stored in httpOnly cookies...
```

Sub-agent session files (in `subagents/` directories) can be replayed but produce empty output since all their messages are sidechain messages.

### Custom Rendering

You can inspect individual elements before final rendering:

```python
from claude_session_player.models import ScreenState, ToolCall
from claude_session_player.parser import read_session
from claude_session_player.renderer import render

state = ScreenState()
for line in read_session("session.jsonl"):
    render(state, line)

# Find all tool calls
tool_calls = [e for e in state.elements if isinstance(e, ToolCall)]
for tc in tool_calls:
    print(f"{tc.tool_name}: {tc.label}")
    if tc.result:
        print(f"  Result: {tc.result[:50]}...")
    if tc.is_error:
        print("  (ERROR)")
```

### Tool Input Abbreviation

Customize how tool inputs are displayed:

```python
from claude_session_player.tools import abbreviate_tool_input

# Bash shows description or command
label = abbreviate_tool_input("Bash", {"description": "Install deps", "command": "npm i"})
# Returns: "Install deps"

# Read shows basename
label = abbreviate_tool_input("Read", {"file_path": "/path/to/config.py"})
# Returns: "config.py"

# Unknown tools return ellipsis
label = abbreviate_tool_input("CustomTool", {})
# Returns: "…"
```

## Message Type Reference

### Visible Message Types

| Type | Subtype | Rendering |
|------|---------|-----------|
| `user` | direct input | `❯` prompt prefix |
| `user` | tool result | Updates tool call with `└` result |
| `user` | local command | Plain text output |
| `assistant` | text block | `●` prefix, markdown passthrough |
| `assistant` | tool_use | `● ToolName(input…)` |
| `assistant` | thinking | `✱ Thinking…` |
| `system` | turn_duration | `✱ Crunched for Xm Ys` |
| `progress` | bash_progress | Updates tool `└` line |
| `progress` | hook_progress | `└ Hook: {name}` |
| `progress` | agent_progress | `└ Agent: working…` |
| `progress` | query_update | `└ Searching: {query}` |
| `progress` | search_results | `└ {count} results` |
| `progress` | waiting_for_task | `└ Waiting: {description}` |

### Invisible Message Types

These message types are intentionally not rendered:

- `user` with `isMeta=true` (skill expansions)
- `user` with `isSidechain=true` (sub-agent messages)
- `assistant` with `isSidechain=true` (sub-agent messages)
- `system` with `subtype="local_command"`
- `system` with `subtype="compact_boundary"` (triggers state clear)
- `summary` (context summary after compaction)
- `file-history-snapshot`
- `queue-operation`
- `pr-link`

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -xvs

# Run with coverage
pytest --cov=claude_session_player --cov-report=term-missing

# Run specific test file
pytest tests/test_renderer.py
```

### Test Structure

```
tests/
├── test_models.py      # Data model tests
├── test_parser.py      # JSONL parsing tests
├── test_formatter.py   # Markdown formatting tests
├── test_renderer.py    # Render function tests
├── test_tools.py       # Tool abbreviation tests
├── test_integration.py # Full session replay tests
├── test_stress.py      # Large session stress tests
├── conftest.py         # Shared fixtures
└── snapshots/          # Expected output snapshots
```

### Project Structure

```
claude_session_player/
├── __init__.py       # Package init, version
├── models.py         # ScreenState, ScreenElement dataclasses
├── renderer.py       # render() function, dispatch logic
├── formatter.py      # to_markdown() and formatting helpers
├── parser.py         # JSONL reading, line classification
├── tools.py          # Tool-specific abbreviation rules
└── cli.py            # CLI entry point
```

## Troubleshooting

### Empty Output

If you get empty output, check if:

1. The session file exists and contains valid JSONL
2. All messages might be `isSidechain=true` (sub-agent file)
3. A `compact_boundary` near the end cleared all content

### Orphan Tool Results

If you see tool results rendered as plain text (not attached to tool calls), the session likely had context compaction that cleared the original tool call.

### Unicode Issues

The tool uses Unicode symbols (`❯`, `●`, `✱`, `└`, `✗`, `…`). Ensure your terminal supports UTF-8 encoding.

## Protocol Reference

Claude Session Player implements the Claude Code Session Protocol (v2.0.76 – v2.1.29). See `claude-code-session-protocol-schema.md` for the complete protocol specification.

## License

MIT License - see LICENSE file for details.
