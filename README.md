# Claude Session Player

Transform Claude Code session logs into readable documentation.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What It Does

Claude Code stores conversation history in JSONL files. Claude Session Player processes these files and renders them as human-readable markdown, showing user prompts, assistant responses, tool calls, and timing information.

```
❯ Can you help me fix the authentication bug?

✱ Thinking…
● I'll investigate the authentication flow.
● Read(auth/login.ts)
  └ import { verify } from 'jsonwebtoken';
    export async function handleLogin...
● Found the issue - missing algorithm parameter.
● Edit(auth/login.ts)
  └ Applied 1 edit

✱ Crunched for 45s
```

## Features

| Feature | Description |
|---------|-------------|
| **Session Replay** | Convert JSONL session files to readable markdown |
| **Live Streaming** | Watch sessions in real-time via SSE |
| **Telegram Integration** | Stream session events to Telegram chats |
| **Slack Integration** | Stream session events to Slack channels |
| **Session Search** | Full-text search across all your Claude Code sessions |
| **REST API** | Programmatic access to all features |

## Installation

```bash
# Clone and install
git clone https://github.com/gutnikov/claude-session-player.git
cd claude-session-player
pip install -e .

# With optional features
pip install -e ".[watcher]"      # File watching + REST API
pip install -e ".[messaging]"    # Telegram + Slack
pip install -e ".[dev]"          # Development
```

**Requirements:** Python 3.12+ (no runtime dependencies for core)

## Quick Start

### Replay a Session

```bash
claude-session-player ~/.claude/projects/-Users-me-myproject/sessions/abc123.jsonl
```

### As a Library

```python
from claude_session_player import replay_session, read_session

lines = read_session("path/to/session.jsonl")
markdown = replay_session(lines)
print(markdown)
```

### Start the Watcher Service

```bash
python -m claude_session_player.watcher --port 8080
```

### Search Sessions via API

```bash
curl "http://localhost:8080/search?q=auth"
```

## Documentation

Full documentation is available in the **[Wiki](https://github.com/gutnikov/claude-session-player/wiki)**:

### Getting Started
- [Installation & Setup](https://github.com/gutnikov/claude-session-player/wiki/Getting-Started)
- [Configuration Reference](https://github.com/gutnikov/claude-session-player/wiki/Configuration)

### Core Features
- [Session Replay Format](https://github.com/gutnikov/claude-session-player/wiki/Session-Replay)
- [Architecture Overview](https://github.com/gutnikov/claude-session-player/wiki/Architecture)

### Watcher Service
- [Watcher Service Guide](https://github.com/gutnikov/claude-session-player/wiki/Watcher-Service)
- [REST API Reference](https://github.com/gutnikov/claude-session-player/wiki/API-Reference)
- [Search Functionality](https://github.com/gutnikov/claude-session-player/wiki/Search)

### Integrations
- [Telegram Setup](https://github.com/gutnikov/claude-session-player/wiki/Telegram-Integration)
- [Slack Setup](https://github.com/gutnikov/claude-session-player/wiki/Slack-Integration)

### Reference
- [Troubleshooting](https://github.com/gutnikov/claude-session-player/wiki/Troubleshooting)
- [Development Guide](https://github.com/gutnikov/claude-session-player/wiki/Development)

## Database Configuration

The session search index uses SQLite for storage:

```yaml
# config.yaml
database:
  # Directory for search.db
  state_dir: "~/.claude-session-player/state"

  # WAL checkpoint interval (seconds, 0 = auto)
  checkpoint_interval: 300

  # Reclaim space on startup
  vacuum_on_startup: false

  # Automatic backups
  backup:
    enabled: false
    path: "~/.claude-session-player/backups"
    keep_count: 3
```

## Index Management

```bash
# Rebuild the search index
claude-session-player index rebuild

# Incremental update
claude-session-player index update

# Show index statistics
claude-session-player index stats

# Verify database integrity
claude-session-player index verify

# Reclaim disk space
claude-session-player index vacuum

# Create backup
claude-session-player index backup --output /path/to/backup.db

# Test search (debugging)
claude-session-player index search "auth bug" --limit 10
```

## Troubleshooting

**Search returns no results:**
1. Check index is built: `claude-session-player index stats`
2. Rebuild if needed: `claude-session-player index rebuild`

**Database corruption:**
1. The service will auto-recover on next start
2. Manual recovery: delete `state/search.db*` and rebuild

**FTS5 not available:**
- This is normal on some systems
- Search still works via LIKE queries (slightly slower)
- Check with: `claude-session-player index stats`

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Claude Session Player                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐ │
│  │  JSONL   │───▶│  Parser   │───▶│ Processor│───▶│ Consumer │ │
│  │  File    │    │           │    │          │    │          │ │
│  └──────────┘    └───────────┘    └──────────┘    └──────────┘ │
│                        │               │               │        │
│                        ▼               ▼               ▼        │
│                   LineType         Events          Markdown     │
│                  (15 types)    (Add/Update/Clear)   Output     │
├─────────────────────────────────────────────────────────────────┤
│                      Watcher Service (Optional)                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐    ┌───────────┐    ┌──────────────────────────┐ │
│  │  File    │───▶│ Transform │───▶│  SSE  │  TG  │  Slack   │ │
│  │ Watcher  │    │           │    └──────────────────────────┘ │
│  └──────────┘    └───────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Finding Session Files

Claude Code stores sessions at:

| OS | Path |
|----|------|
| macOS/Linux | `~/.claude/projects/<encoded-path>/sessions/*.jsonl` |
| Windows | `%USERPROFILE%\.claude\projects\<encoded-path>\sessions\*.jsonl` |

Path encoding: `/` → `-`, `-` → `--`

Example: `/Users/me/my-project` → `-Users-me-my--project`

## API Quick Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/attach` | POST | Attach destination to session |
| `/detach` | POST | Detach destination |
| `/sessions` | GET | List watched sessions |
| `/sessions/{id}/events` | GET | SSE event stream |
| `/search` | GET | Search sessions |
| `/health` | GET | Health check |

See [API Reference](https://github.com/gutnikov/claude-session-player/wiki/API-Reference) for details.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=claude_session_player --cov-report=term-missing
```

See [Development Guide](https://github.com/gutnikov/claude-session-player/wiki/Development) for details.

## License

MIT License - see LICENSE file for details.
