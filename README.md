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
from claude_session_player import replay_session, read_session

# Load and replay a session
lines = read_session("path/to/session.jsonl")
markdown = replay_session(lines)
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

### High-Level API

#### `replay_session(lines: list[dict]) -> str`

Replay a session and return markdown output. This is the simplest way to use the library.

```python
from claude_session_player import replay_session, read_session

lines = read_session("session.jsonl")
markdown = replay_session(lines)
print(markdown)
```

#### `read_session(path: str) -> list[dict]`

Read and parse all lines from a JSONL session file.

```python
from claude_session_player import read_session

lines = read_session("session.jsonl")
for line in lines:
    print(line.get("type"))
```

### Event-Driven API

For more control, use the event-driven architecture directly:

```python
from claude_session_player import (
    ProcessingContext,
    ScreenStateConsumer,
    process_line,
    read_session,
)

# Create context and consumer
context = ProcessingContext()
consumer = ScreenStateConsumer()

# Process each line into events, feed to consumer
for line in read_session("session.jsonl"):
    for event in process_line(context, line):
        consumer.handle(event)

# Get the final markdown output
markdown = consumer.to_markdown()

# Or access the internal state
for block in consumer.blocks:
    print(f"{block.type}: {block.id}")
```

### Event Types

The processor emits three event types:

```python
from claude_session_player import AddBlock, UpdateBlock, ClearAll

# AddBlock: Add a new block to the consumer
# UpdateBlock: Update an existing block (e.g., add tool result)
# ClearAll: Clear all blocks (on compaction)
```

### Block Types

Blocks represent visual elements in the output:

```python
from claude_session_player import Block, BlockType

# BlockType variants:
BlockType.USER        # User message (❯)
BlockType.ASSISTANT   # Assistant text (●)
BlockType.TOOL_CALL   # Tool invocation (● ToolName(...))
BlockType.THINKING    # Thinking indicator (✱ Thinking…)
BlockType.DURATION    # Turn timing (✱ Crunched for...)
BlockType.SYSTEM      # System output
```

### Block Content Types

Each block type has a specific content type:

```python
from claude_session_player import (
    UserContent,       # text: str
    AssistantContent,  # text: str, request_id: str | None
    ToolCallContent,   # tool_name: str, tool_use_id: str, label: str,
                       # result: str | None, is_error: bool, progress_text: str | None,
                       # request_id: str | None
    ThinkingContent,   # request_id: str | None
    DurationContent,   # duration_ms: int
    SystemContent,     # text: str
)
```

### Line Classification

Classify JSONL lines into semantic types:

```python
from claude_session_player import classify_line, LineType

line_type = classify_line({"type": "user", "message": {"content": "hi"}})
assert line_type == LineType.USER_INPUT

# LineType variants:
# User messages: USER_INPUT, TOOL_RESULT, LOCAL_COMMAND_OUTPUT
# Assistant messages: ASSISTANT_TEXT, TOOL_USE, THINKING
# System messages: TURN_DURATION, COMPACT_BOUNDARY
# Progress: BASH_PROGRESS, HOOK_PROGRESS, AGENT_PROGRESS,
#           QUERY_UPDATE, SEARCH_RESULTS, WAITING_FOR_TASK
# Skip: INVISIBLE
```

## Advanced Usage

### Inspecting Individual Blocks

```python
from claude_session_player import (
    ProcessingContext, ScreenStateConsumer, process_line,
    read_session, BlockType, ToolCallContent
)

context = ProcessingContext()
consumer = ScreenStateConsumer()

for line in read_session("session.jsonl"):
    for event in process_line(context, line):
        consumer.handle(event)

# Find all tool calls
for block in consumer.blocks:
    if block.type == BlockType.TOOL_CALL:
        content = block.content  # ToolCallContent
        print(f"{content.tool_name}: {content.label}")
        if content.result:
            print(f"  Result: {content.result[:50]}...")
        if content.is_error:
            print("  (ERROR)")
```

### Handling Context Compaction

Claude Code uses "context compaction" to manage long conversations. When a `compact_boundary` is encountered, all prior content is cleared:

```python
# After compaction, only post-compaction content is visible
# The ClearAll event is emitted, and the consumer clears its state
```

### Sub-Agent Sessions

Task tool invocations spawn sub-agents. Their internal messages have `isSidechain=True` and are classified as `INVISIBLE`. The Task result shows a collapsed summary:

```
● Task(Analyze authentication system)
  └ The codebase uses JWT tokens stored in httpOnly cookies...
```

Sub-agent session files (in `subagents/` directories) can be replayed but produce empty output since all their messages are sidechain messages.

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
pytest tests/test_parser.py
```

### Test Structure

```
tests/
├── test_parser.py      # JSONL parsing tests
├── test_processor.py   # Event processor tests
├── test_consumer.py    # Consumer state tests
├── test_formatter.py   # Formatting utility tests
├── test_tools.py       # Tool abbreviation tests
├── test_integration.py # Full session replay tests
├── test_stress.py      # Large session stress tests
├── conftest.py         # Shared fixtures
└── snapshots/          # Expected output snapshots
```

### Project Structure

```
claude_session_player/
├── __init__.py       # Package init, public API exports
├── events.py         # Event and Block dataclasses
├── processor.py      # process_line() event generator
├── consumer.py       # ScreenStateConsumer, replay_session()
├── formatter.py      # Duration formatting, result truncation
├── parser.py         # JSONL reading, line classification
├── tools.py          # Tool-specific abbreviation rules
└── cli.py            # CLI entry point
```

### Architecture

The player uses an event-driven architecture:

```
JSONL line → classify_line() → process_line() → [Event...] → Consumer → to_markdown()
```

1. **Parser** (`parser.py`): Reads JSONL, classifies lines into `LineType` variants
2. **Processor** (`processor.py`): Generates events (`AddBlock`, `UpdateBlock`, `ClearAll`)
3. **Consumer** (`consumer.py`): Builds state from events, produces markdown
4. **Formatter** (`formatter.py`): Utility functions for duration and truncation

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

## Session Watcher Service

The Session Watcher Service is an optional component that watches Claude Code session files for changes and streams processed events to subscribers via Server-Sent Events (SSE). It also supports sending notifications to Telegram and Slack channels.

### Installation

```bash
# Install with watcher dependencies
pip install "claude-session-player[watcher]"

# Or install dependencies directly
pip install pyyaml watchfiles aiohttp
```

For messaging support (Telegram and Slack):

```bash
# Install with messaging dependencies
pip install "claude-session-player[messaging]"

# Or install dependencies directly
pip install aiogram slack-sdk
```

### Running the Service

```bash
# Start with defaults (localhost:8080)
python -m claude_session_player.watcher

# Custom configuration
python -m claude_session_player.watcher \
    --host 0.0.0.0 \
    --port 9000 \
    --config /etc/watcher/config.yaml \
    --state-dir /var/lib/watcher/state \
    --log-level DEBUG
```

Command-line options:
- `--host`: HTTP server host (default: `127.0.0.1`)
- `--port`: HTTP server port (default: `8080`)
- `--config`: Path to config.yaml (default: `config.yaml`)
- `--state-dir`: Directory for state files (default: `state`)
- `--log-level`: Logging level (default: `INFO`)

### Configuration

The service uses a YAML configuration file:

```yaml
# config.yaml

# Bot credentials (optional)
bots:
  telegram:
    token: "123456:ABC-DEF..."  # From @BotFather
  slack:
    token: "xoxb-..."           # Bot User OAuth Token

# Sessions and their destinations (persisted across restarts)
sessions:
  my-session:
    path: "/path/to/session.jsonl"
    destinations:
      telegram:
        - chat_id: "123456789"
      slack:
        - channel: "C0123456789"
```

### Messaging Integration

The watcher service can send session events to Telegram and Slack channels in addition to SSE.

#### Telegram Setup

1. Create a bot via [@BotFather](https://t.me/botfather):
   - Send `/newbot` and follow the prompts
   - Copy the bot token

2. Add the token to your config:
   ```yaml
   # config.yaml
   bots:
     telegram:
       token: "123456:ABC-DEF..."
   ```

3. Add the bot to your target chat/group

4. Get your chat ID:
   - For private chats: message the bot, then check `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - For groups: temporarily add [@userinfobot](https://t.me/userinfobot)

#### Slack Setup

1. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps)
   - Click "Create New App" → "From scratch"
   - Name your app and select your workspace

2. Configure permissions:
   - Go to "OAuth & Permissions"
   - Add Bot Token Scopes: `chat:write`, `chat:write.public`
   - Click "Install to Workspace"

3. Copy the Bot User OAuth Token (`xoxb-...`) to your config:
   ```yaml
   bots:
     slack:
       token: "xoxb-..."
   ```

4. For private channels, invite the bot: `/invite @your-bot-name`

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/attach` | POST | Attach a messaging destination to a session |
| `/detach` | POST | Detach a messaging destination |
| `/sessions` | GET | List all sessions and their destinations |
| `/sessions/{id}/events` | GET | SSE stream of session events |
| `/health` | GET | Health check with bot status |

#### POST /attach

Attach a messaging destination to a session.

```bash
# Attach a Telegram chat
curl -X POST http://localhost:8080/attach \
    -H "Content-Type: application/json" \
    -d '{
        "session_id": "my-session",
        "path": "/path/to/session.jsonl",
        "destination": {"type": "telegram", "chat_id": "123456789"}
    }'

# Attach a Slack channel
curl -X POST http://localhost:8080/attach \
    -H "Content-Type: application/json" \
    -d '{
        "session_id": "my-session",
        "destination": {"type": "slack", "channel": "C0123456789"}
    }'
```

Request body:
- `session_id` (required): Unique identifier for the session
- `path` (required on first attach): Absolute path to the JSONL file
- `destination` (required): Destination object with `type` and identifier
- `replay_count` (optional): Number of past events to replay on attach (default: 0)

Response (201 Created):
```json
{
    "attached": true,
    "session_id": "my-session",
    "destination": {"type": "telegram", "chat_id": "123456789"},
    "replayed_events": 0
}
```

Error responses:
- 400: Invalid request (missing fields, invalid destination type)
- 401: Bot token not configured
- 403: Bot credential validation failed
- 404: Session path not found

#### POST /detach

Detach a messaging destination from a session.

```bash
curl -X POST http://localhost:8080/detach \
    -H "Content-Type: application/json" \
    -d '{
        "session_id": "my-session",
        "destination": {"type": "telegram", "chat_id": "123456789"}
    }'
```

Response: 204 No Content

#### GET /sessions

List all sessions and their destinations.

```bash
curl http://localhost:8080/sessions
```

Response:
```json
{
    "sessions": [
        {
            "session_id": "my-session",
            "path": "/path/to/session.jsonl",
            "sse_clients": 2,
            "destinations": {
                "telegram": [{"chat_id": "123456789"}],
                "slack": [{"channel": "C0123456789"}]
            }
        }
    ]
}
```

#### GET /sessions/{session_id}/events

Subscribe to SSE events for a session.

```bash
curl -N -H "Accept: text/event-stream" \
    http://localhost:8080/sessions/my-session/events
```

Optional header for replay:
```bash
curl -N -H "Accept: text/event-stream" \
    -H "Last-Event-ID: evt_020" \
    http://localhost:8080/sessions/my-session/events
```

#### GET /health

Health check endpoint with bot status.

```bash
curl http://localhost:8080/health
```

Response:
```json
{
    "status": "healthy",
    "sessions_watched": 3,
    "uptime_seconds": 3600,
    "bots": {
        "telegram": "configured",
        "slack": "not_configured"
    }
}
```

### SSE Event Format

Events are sent as Server-Sent Events with the following format:

```
id: evt_001
event: add_block
data: {"block_id":"b1","type":"assistant","content":{"text":"Hello"},"request_id":"req_123"}

id: evt_002
event: update_block
data: {"block_id":"b1","content":{"text":"Hello, world!"}}

id: evt_003
event: clear_all
data: {}

id: session_ended
event: session_ended
data: {"reason":"file_deleted"}
```

Event types:
- `add_block` — New block added (user message, assistant text, tool call, etc.)
- `update_block` — Existing block updated (tool result, progress update)
- `clear_all` — Context compaction occurred, all previous content cleared
- `session_ended` — Session file deleted or detached

### Reconnection and Replay

The service maintains a buffer of the last 20 events per session. When a client reconnects with the `Last-Event-ID` header, events after that ID are replayed. If the ID is unknown or evicted, all buffered events are replayed.

When attaching a messaging destination with `replay_count`, the last N events are sent as a batched catch-up message.

### State Persistence

The service persists processing state to disk, allowing it to resume from the last known position after restart. State files are stored in the state directory (`state/` by default) as JSON files named `{session_id}.json`.

### Example: Subscribing with Python

```python
import aiohttp
import asyncio

async def subscribe_to_session(session_id: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"http://localhost:8080/sessions/{session_id}/events",
            headers={"Accept": "text/event-stream"}
        ) as response:
            async for line in response.content:
                line = line.decode("utf-8").strip()
                if line.startswith("data:"):
                    data = line[5:].strip()
                    print(f"Received: {data}")

asyncio.run(subscribe_to_session("my-session"))
```

### Troubleshooting

#### Bot Not Responding

- **Telegram**: Ensure the bot is added to the chat and has permission to send messages. For groups, the bot may need admin permissions.
- **Slack**: Ensure the bot is invited to the channel. For private channels, use `/invite @bot-name`.

#### Rate Limits

The service automatically rate-limits message updates to stay within platform limits:
- Telegram: Updates debounced to ~2/second per chat
- Slack: Updates debounced to ~0.5/second per channel

#### Missing Messages After Restart

Message state (which Telegram/Slack messages to update) is ephemeral and not persisted. After a service restart, new events will create new messages rather than updating existing ones.

## Breaking Changes

### v0.5.0

- **API Change**: `/watch` and `/unwatch` endpoints removed
  - Use `/attach` and `/detach` instead
  - New endpoints support messaging destinations (Telegram, Slack)
  - `path` is now required only on first attach

- **Config Change**: `config.yaml` format updated
  - New `bots` section for Telegram/Slack credentials
  - Sessions now include `destinations` field
  - Old format auto-migrated on first load

## License

MIT License - see LICENSE file for details.
