# CLAUDE.md - Claude Code Context for Claude Session Player

## Project Overview

Claude Session Player is a Python tool that replays Claude Code JSONL session files as readable markdown output. It uses an event-driven architecture where each JSONL line is processed into events that build the final output state.

## Specifications

Design documents for major features:

- `.claude/specs/sqlite-search-index.md` - SQLite search index design
- `.claude/specs/session-search-api.md` - Search API design
- `.claude/specs/messaging-integration.md` - Telegram/Slack messaging integration
- `.claude/specs/event-driven-renderer.md` - Event-driven architecture spec
- `.claude/specs/claude-session-player.md` - Original spec

## Quick Commands

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -xvs

# Run with coverage report
pytest --cov=claude_session_player --cov-report=term-missing

# Replay a session file
claude-session-player examples/projects/orca/sessions/014d9d94-xxx.jsonl

# Or via Python module
python -m claude_session_player.cli path/to/session.jsonl

# Search sessions via API
curl "http://localhost:8080/search?q=auth"
```

## Architecture

### Core Flow

```
JSONL line → classify_line() → process_line() → [Event...] → Consumer → to_markdown()
```

1. **Parser** (`parser.py`): Reads JSONL, classifies lines into 15 `LineType` variants
2. **Processor** (`processor.py`): Converts lines to events (`AddBlock`, `UpdateBlock`, `ClearAll`)
3. **Consumer** (`consumer.py`): Handles events, builds state, produces markdown
4. **Formatter** (`formatter.py`): Utility functions for duration formatting and result truncation

### Event Types

```python
# Add a new block to the output
AddBlock(block: Block)

# Update an existing block (e.g., add tool result, update progress)
UpdateBlock(block_id: str, content: BlockContent)

# Clear all blocks (on context compaction)
ClearAll()
```

### Block Types

```python
# Block types with their content
BlockType.USER        → UserContent(text: str)
BlockType.ASSISTANT   → AssistantContent(text: str, request_id: str | None)
BlockType.TOOL_CALL   → ToolCallContent(tool_name, tool_use_id, label, result, is_error, progress_text, request_id)
BlockType.THINKING    → ThinkingContent(request_id: str | None)
BlockType.DURATION    → DurationContent(duration_ms: int)
BlockType.SYSTEM      → SystemContent(text: str)
```

### Key Data Structures

```python
# Processing context maintains state between lines
ProcessingContext:
    tool_use_id_to_block_id: dict[str, str]  # Maps tool_use_id → block_id
    current_request_id: str | None           # Groups consecutive assistant blocks

# Consumer builds final state from events
ScreenStateConsumer:
    blocks: list[Block]                      # Ordered visual blocks
    block_index: dict[str, int]              # block_id → index for updates

# Block represents a visual element
Block:
    id: str                                  # Unique identifier
    type: BlockType                          # USER, ASSISTANT, TOOL_CALL, etc.
    content: BlockContent                    # Type-specific content
```

### Line Type Classification

```python
# User messages
USER_INPUT, TOOL_RESULT, LOCAL_COMMAND_OUTPUT

# Assistant messages
ASSISTANT_TEXT, TOOL_USE, THINKING

# System messages
TURN_DURATION, COMPACT_BOUNDARY

# Progress messages (update existing tool calls)
BASH_PROGRESS, HOOK_PROGRESS, AGENT_PROGRESS,
QUERY_UPDATE, SEARCH_RESULTS, WAITING_FOR_TASK

# Skip
INVISIBLE
```

### Search Database

The `SearchDatabase` class provides SQLite-based persistence for the session search index.

- `watcher/search_db.py` - SQLite database wrapper
  - Schema management with automatic migration
  - CRUD operations for sessions
  - FTS5 full-text search with graceful fallback
  - Maintenance operations (backup, vacuum, checkpoint)

#### Database Schema

```sql
-- sessions: Session metadata with project info, summary, timestamps
-- sessions_fts: Full-text search virtual table (FTS5)
-- index_metadata: Index statistics and state
-- file_mtimes: Incremental update tracking by file mtime
```

#### Search Ranking

Results are ranked using weighted scoring:
- Summary match: 2.0 per term
- Exact phrase: +1.0 bonus
- Project match: 1.0 per term
- Recency: 0.0-1.0 (decays over 30 days)

## Coding Conventions

### Python Version

- Target Python 3.12+
- Use `from __future__ import annotations` for forward references
- Use `X | None` union syntax (not `Optional[X]`)
- Use dataclasses, not attrs or pydantic

### Style Guidelines

- No runtime dependencies (stdlib only)
- Simple if/elif chains (no match/case for 3.9 compat during testing)
- Table-driven dispatch preferred over long conditionals
- Defensive handling: unknown types → INVISIBLE, missing fields → empty/None

### Testing

- Tests in `tests/` directory
- Fixtures in `tests/conftest.py`
- Snapshot tests in `tests/snapshots/`
- All tests use pytest
- Target: comprehensive coverage (currently 98%)

## Important Patterns

### Tool Result Matching

Tool results match to tool calls via `tool_use_id`:

```python
# When tool_use is processed:
context.tool_use_id_to_block_id[tool_use_id] = block_id

# When tool_result arrives:
block_id = context.tool_use_id_to_block_id.get(tool_use_id)
if block_id:
    yield UpdateBlock(block_id, updated_content)
```

### Request ID Grouping

Consecutive assistant blocks with the same `requestId` render without blank lines between them. The consumer tracks `request_id` in block content to determine grouping.

### Context Compaction

When `compact_boundary` is encountered, emit `ClearAll`:

```python
def _process_compact_boundary(context, line):
    context.clear()
    yield ClearAll()
```

### Sidechain Messages

Sub-agent messages have `isSidechain=True` and are classified as `INVISIBLE`:

```python
if line.get("isSidechain") and msg_type in ("user", "assistant"):
    return LineType.INVISIBLE
```

## File Locations

### Source Code
- `claude_session_player/events.py` - Event and Block dataclasses
- `claude_session_player/processor.py` - Line to event processing
- `claude_session_player/consumer.py` - Event consumer, markdown output
- `claude_session_player/parser.py` - JSONL parsing, line classification
- `claude_session_player/formatter.py` - Duration formatting, result truncation
- `claude_session_player/tools.py` - Tool input abbreviation rules
- `claude_session_player/cli.py` - CLI entry point

### Watcher Module
- `claude_session_player/watcher/__init__.py` - Public exports
- `claude_session_player/watcher/__main__.py` - CLI entry point for watcher service
- `claude_session_player/watcher/service.py` - Main WatcherService orchestration
- `claude_session_player/watcher/api.py` - REST API endpoints (attach/detach/search)
- `claude_session_player/watcher/sse.py` - SSE connection management
- `claude_session_player/watcher/destinations.py` - Destination lifecycle management
- `claude_session_player/watcher/telegram_publisher.py` - Telegram Bot API integration
- `claude_session_player/watcher/slack_publisher.py` - Slack Web API integration
- `claude_session_player/watcher/message_state.py` - Turn-based message grouping
- `claude_session_player/watcher/debouncer.py` - Rate limiting for message updates
- `claude_session_player/watcher/event_buffer.py` - Per-session event ring buffer
- `claude_session_player/watcher/transformer.py` - Stateless line-to-event transformer
- `claude_session_player/watcher/file_watcher.py` - File change detection (watchfiles)
- `claude_session_player/watcher/config.py` - Session and bot config management (YAML)
- `claude_session_player/watcher/state.py` - Processing state persistence (JSON)
- `claude_session_player/watcher/deps.py` - Optional dependency checking

### Search Module
- `claude_session_player/watcher/search_db.py` - SQLite search database
- `claude_session_player/watcher/indexer.py` - Session indexer (path encoding, metadata extraction)
- `claude_session_player/watcher/search.py` - Search engine (query parsing, ranking)
- `claude_session_player/watcher/search_state.py` - Search state manager (pagination)
- `claude_session_player/watcher/rate_limit.py` - Token bucket rate limiter
- `claude_session_player/watcher/bot_router.py` - Webhook router for Slack/Telegram
- `claude_session_player/watcher/slack_commands.py` - Slack /search command handler
- `claude_session_player/watcher/telegram_commands.py` - Telegram /search command handler
- `claude_session_player/watcher/telegram_bot.py` - Telegram webhook setup and polling

### Database Files
- `{state_dir}/search.db` - SQLite database file
- `{state_dir}/search.db-wal` - WAL journal (auto-managed)
- `{state_dir}/search.db-shm` - Shared memory (auto-managed)

### Tests
- `tests/test_parser.py` - Parser tests
- `tests/test_processor.py` - Processor tests
- `tests/test_consumer.py` - Consumer tests
- `tests/test_formatter.py` - Formatter tests
- `tests/test_tools.py` - Tool abbreviation tests
- `tests/test_integration.py` - Full session replay tests
- `tests/test_stress.py` - Stress tests with large sessions
- `tests/watcher/test_*.py` - Watcher module tests
- `tests/watcher/test_e2e.py` - End-to-end watcher tests
- `tests/watcher/test_messaging_integration.py` - Messaging integration tests
- `tests/watcher/test_indexer.py` - Session indexer tests
- `tests/watcher/test_search.py` - Search engine tests
- `tests/watcher/test_search_state.py` - Search state manager tests
- `tests/watcher/test_rate_limit.py` - Rate limiter tests
- `tests/watcher/test_api_search.py` - Search API endpoint tests
- `tests/watcher/test_slack_commands.py` - Slack command handler tests
- `tests/watcher/test_telegram_commands.py` - Telegram command handler tests
- `tests/watcher/test_search_e2e.py` - End-to-end search flow tests
- `tests/watcher/test_search_db.py` - SQLite database unit tests
- `tests/watcher/test_search_db_fts.py` - FTS5 full-text search tests
- `tests/watcher/test_search_db_ranking.py` - Search ranking algorithm tests
- `tests/watcher/test_search_db_maintenance.py` - Database maintenance tests
- `tests/watcher/test_search_db_integration.py` - SQLite integration tests

### Example Data
- `examples/projects/*/sessions/*.jsonl` - Real session files
- `examples/projects/*/sessions/subagents/*.jsonl` - Sub-agent sessions
- `tests/snapshots/*.md` - Expected output snapshots

### Documentation
- `README.md` - User documentation
- `CLAUDE.md` - This file (Claude Code context)
- `.claude/specs/claude-session-player.md` - Original spec
- `.claude/specs/event-driven-renderer.md` - Event-driven architecture spec
- `claude-code-session-protocol-schema.md` - Protocol reference
- `issues/worklogs/*.md` - Development history

## Common Tasks

### Adding a New Message Type

1. Add variant to `LineType` enum in `parser.py`
2. Add classification logic in `classify_line()` or helper functions
3. Add handler in `processor.py` following the `_process_*` pattern
4. Add tests in appropriate test files

### Adding a New Tool

Add entry to `_TOOL_RULES` in `tools.py`:

```python
_TOOL_RULES = {
    # ...
    "NewTool": ("field_name", None, "truncate"),  # or "basename"
}
```

### Debugging Session Replay

```python
from claude_session_player import (
    ProcessingContext, ScreenStateConsumer, process_line, read_session
)

context = ProcessingContext()
consumer = ScreenStateConsumer()

for i, line in enumerate(read_session("session.jsonl")):
    events = list(process_line(context, line))
    for event in events:
        print(f"{i}: {type(event).__name__}")
        consumer.handle(event)

print(consumer.to_markdown())
```

### Running the Watcher Service

```bash
# Start with defaults
python -m claude_session_player.watcher

# Custom configuration
python -m claude_session_player.watcher \
    --host 0.0.0.0 \
    --port 9000 \
    --config /path/to/config.yaml \
    --state-dir /path/to/state \
    --log-level DEBUG
```

### Attaching a Messaging Destination

```bash
# Attach a Telegram chat to a session
curl -X POST http://localhost:8080/attach \
    -H "Content-Type: application/json" \
    -d '{"session_id": "my-session", "path": "/path/to/session.jsonl", "destination": {"type": "telegram", "chat_id": "123456789"}}'

# Attach a Slack channel
curl -X POST http://localhost:8080/attach \
    -H "Content-Type: application/json" \
    -d '{"session_id": "my-session", "destination": {"type": "slack", "channel": "C0123456789"}}'
```

### Detaching a Destination

```bash
curl -X POST http://localhost:8080/detach \
    -H "Content-Type: application/json" \
    -d '{"session_id": "my-session", "destination": {"type": "telegram", "chat_id": "123456789"}}'
```

### Subscribing to Session Events (SSE)

```bash
curl -N -H "Accept: text/event-stream" \
    http://localhost:8080/sessions/my-session/events
```

### Searching Sessions

```python
import asyncio
from pathlib import Path
from claude_session_player.watcher.indexer import SessionIndexer, IndexConfig
from claude_session_player.watcher.search import SearchEngine

async def search_sessions():
    # Build index
    config = IndexConfig(paths=[Path("~/.claude/projects").expanduser()])
    indexer = SessionIndexer(config)
    await indexer.get_index()

    # Search
    engine = SearchEngine(indexer)
    params = engine.parse_query("auth bug")
    results = await engine.search(params)

    for session in results.results:
        print(f"{session.project_display_name}: {session.summary}")

asyncio.run(search_sessions())
```

### Searching via REST API

```bash
# Search with query
curl "http://localhost:8080/search?q=auth"

# Search with filters
curl "http://localhost:8080/search?q=auth&project=trello&limit=10"

# List all projects
curl "http://localhost:8080/projects"

# Preview a session
curl "http://localhost:8080/sessions/930c1604-5137-4684-a344-863b511a914c/preview"
```

### Working with the Search Database

```python
from pathlib import Path
from claude_session_player.watcher.search_db import SearchDatabase, SearchFilters

async def example():
    # Connect to database
    db = SearchDatabase(Path("~/.claude-session-player/state").expanduser())
    await db.initialize()

    # Search sessions
    results, total = await db.search(SearchFilters(
        query="auth bug",
        project="trello",
    ))

    for session in results:
        print(f"{session.project_display_name}: {session.summary}")

    # Get ranked results with relevance scoring
    ranked, total = await db.search_ranked(SearchFilters(query="auth"))
    for result in ranked:
        print(f"[{result.score:.2f}] {result.session.summary}")

    # Get statistics
    stats = await db.get_stats()
    print(f"Indexed: {stats['total_sessions']} sessions")
    print(f"FTS5 available: {stats['fts_available']}")

    # Cleanup
    await db.close()
```

## Watcher Architecture

The watcher service uses a layered architecture:

```
HTTP Request → WatcherAPI → WatcherService → Components
                                   ↓
         ┌─────────────────────────┼─────────────────────────┐
         │              │          │          │              │
         ▼              ▼          ▼          ▼              ▼
   SSEManager    TelegramPub  SlackPub  DestinationMgr  FileWatcher
         │              │          │          │              │
         └──────────────┴──────────┴──────────┘              │
                               │                             │
                               ▼                             │
                    MessageStateTracker ←────────────────────┘
                               │
                               ▼
                       MessageDebouncer
```

### Event Flow (File Change → Messaging)

```python
FileWatcher detects change
    ↓
WatcherService._on_file_change(session_id, lines)
    ↓
transformer.transform(lines, context) → events
    ↓
For each event:
    ├─→ EventBufferManager.add_event() → event_id
    ├─→ SSEManager.broadcast()
    └─→ MessageStateTracker.handle_event() → MessageAction
            ├─→ SendNewMessage → TelegramPublisher / SlackPublisher
            └─→ UpdateExistingMessage → MessageDebouncer → Publishers
```

### Key Components

- **WatcherService**: Orchestrates all components, handles lifecycle
- **WatcherAPI**: REST endpoints (POST /attach, POST /detach, GET /sessions, etc.)
- **FileWatcher**: Uses `watchfiles` for cross-platform file change detection
- **transformer()**: Stateless function that converts JSONL lines to events
- **EventBufferManager**: Per-session ring buffer (last 20 events) for replay
- **SSEManager**: Manages SSE connections, broadcasts events, handles keepalive
- **DestinationManager**: Track attached destinations, manage keep-alive timer
- **TelegramPublisher**: Telegram Bot API via aiogram (send/edit messages)
- **SlackPublisher**: Slack Web API via slack-sdk (post/update messages)
- **MessageStateTracker**: Map turns to message IDs, handle turn finalization
- **MessageDebouncer**: Rate-limit message updates per destination
- **ConfigManager**: Persists watched sessions and bot config to `config.yaml`
- **StateManager**: Persists processing context and file position per session

### Search Components

- **SearchDatabase**: SQLite-based search index with FTS5 full-text search
- **SessionIndexer**: Scans `.claude/projects` directories, builds/persists session index
- **SearchEngine**: Query parsing, filtering, and ranking algorithm
- **SearchStateManager**: Manages pagination state per chat for bot interactions
- **RateLimiter**: Token bucket rate limiter for API and bot commands
- **BotRouter**: Routes Slack/Telegram webhooks to command handlers
- **SlackCommandHandler**: Handles Slack `/search` command and interactions
- **TelegramCommandHandler**: Handles Telegram `/search` command and callbacks

### Configuration (config.yaml)

```yaml
bots:
  telegram:
    token: "BOT_TOKEN"
  slack:
    token: "xoxb-..."

# Search index configuration
index:
  paths:
    - "~/.claude/projects"
  refresh_interval: 300
  include_subagents: false

# SQLite database settings
database:
  state_dir: "~/.claude-session-player/state"
  checkpoint_interval: 300
  vacuum_on_startup: false
  backup:
    enabled: false
    path: "~/.claude-session-player/backups"
    keep_count: 3

sessions:
  my-session:
    path: "/path/to/session.jsonl"
    destinations:
      telegram:
        - chat_id: "123456789"
      slack:
        - channel: "C0123456789"
```

## Known Limitations

1. **Subagent files produce empty output**: By design, `isSidechain=True` messages are invisible
2. **No streaming/animated output**: Output is static markdown
3. **No ANSI colors**: Plain text output only
4. **Orphan results**: Tool results from before compaction render as SystemOutput

## Protocol Notes

- Session protocol version: v2.0.76 – v2.1.29
- `parentToolUseID` is at top level of progress messages, not in `data`
- `toolUseResult` for Task tools is at top level, contains collapsed result
- Content can be string, list of blocks, or null
- List content may include non-text blocks (filter for `type: "text"`)
