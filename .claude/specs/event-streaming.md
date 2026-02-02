# Claude Code Event Streaming

## Overview

claude-code-hub is a service that provides an API to create, resume, stop Claude Code sessions, post messages to them, and subscribe to session events. Behind the API, `ClaudeCodeClient` manages tmux sessions running Claude Code CLI. This spec covers how events flow back from Claude Code sessions to the service and out to subscribers.

## Goals

- Stream structured events from Claude Code sessions in near-real-time
- Capture at minimum: assistant messages, tool calls, permission/confirmation prompts, session lifecycle (start, stop)
- Support multiple concurrent sessions
- Expose events to external consumers (e.g. Slack bot) via the service API

## Approach Analysis

### Option A: Claude Code Hooks (Recommended)

Claude Code has a built-in hook system that fires shell commands on lifecycle events. Hooks receive structured JSON on stdin with full context.

**Available events (12 total):**

| Event | Fires when | Key data on stdin |
|-------|-----------|-------------------|
| `SessionStart` | Session begins/resumes | `source`, `model` |
| `UserPromptSubmit` | User sends a prompt | `prompt` text |
| `PreToolUse` | Before tool executes | `tool_name`, `tool_input` |
| `PostToolUse` | After tool succeeds | `tool_name`, `tool_input`, `tool_response` |
| `PostToolUseFailure` | After tool fails | `tool_name`, `error` |
| `PermissionRequest` | Permission dialog appears | `tool_name`, `tool_input`, `permission_suggestions` |
| `Notification` | Notification fires | `message`, `title`, `notification_type` |
| `Stop` | Claude finishes responding | `stop_hook_active` |
| `SubagentStart` | Subagent spawns | `agent_id`, `agent_type` |
| `SubagentStop` | Subagent finishes | `agent_id`, `agent_type` |
| `PreCompact` | Before context compaction | `trigger` |
| `SessionEnd` | Session terminates | `reason` |

**Common JSON fields on stdin (all events):**
```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/current/working/dir",
  "hook_event_name": "PostToolUse"
}
```

**How it works:**
- Configure hooks in `.claude/settings.json` or `~/.claude/settings.json`
- Each hook runs a shell command that receives event JSON on stdin
- Hook command can be a script that posts to an HTTP endpoint, writes to a FIFO, or appends to a file
- Exit code 0 = allow, exit code 2 = block (for `PreToolUse`/`UserPromptSubmit`)
- All matching hooks run in parallel; default timeout 600s

**Configuration example:**
```json
{
  "hooks": {
    "PostToolUse": [{ "hooks": [{ "type": "command", "command": "python3 emit_event.py" }] }],
    "Stop": [{ "hooks": [{ "type": "command", "command": "python3 emit_event.py" }] }],
    "PermissionRequest": [{ "hooks": [{ "type": "command", "command": "python3 emit_event.py" }] }],
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "python3 emit_event.py" }] }],
    "SessionEnd": [{ "hooks": [{ "type": "command", "command": "python3 emit_event.py" }] }]
  }
}
```

**Pros:**
- Structured JSON — no screen scraping or ANSI stripping
- Covers all lifecycle events including permission prompts
- Hook can block/allow actions (interactive control from Slack is possible)
- Works regardless of tmux — hooks are a Claude Code feature
- Full tool call details: name, input, response
- `transcript_path` gives access to the full conversation JSONL

**Cons:**
- No "assistant message text" event — `Stop` fires when Claude finishes but doesn't include the response text in the hook input. The response must be read from `transcript_path`.
- Hook scripts run as child processes — adds overhead per event
- Hook configuration is per-project or per-user, not per-session
- Hooks snapshot at startup; changes require `/hooks` review or restart

**Gap — getting assistant message text:**
The hook system provides tool calls and lifecycle events but does not directly include Claude's text responses. Two sub-options:

- **A1: Read `transcript_path`** — The `Stop` hook receives `transcript_path` pointing to a JSONL file. Parse the last assistant message from it. This is the intended approach.
- **A2: Combine with `capture-pane`** — On `Stop`, snapshot the screen for the rendered response. Lossy but simple.

---

### Option B: tmux `pipe-pane` (Raw Output Stream)

Pipes the raw byte stream from the pane to a shell command or file.

```python
pane.cmd("pipe-pane", "-O", "cat >> /tmp/claude-output.log")
```

**Pros:**
- True real-time streaming — push-based, no polling
- Captures everything visible on screen as it renders
- Simple to set up via libtmux (`pane.cmd()`)

**Cons:**
- Raw terminal output — full of ANSI escape sequences, cursor movements, screen redraws
- Claude Code's TUI renders complex layouts (boxes, spinners, status bars) — parsing meaningful messages from the raw byte stream is extremely difficult
- No structured data — cannot distinguish "assistant message" from "UI chrome"
- Only one pipe per pane at a time
- No semantic events (no way to know "this is a permission prompt" vs "this is a response")

---

### Option C: tmux Control Mode (`-CC`)

Attach to the tmux server in control mode to receive `%output` notifications for all pane activity.

```python
proc = subprocess.Popen(["tmux", "-C", "attach", "-t", session], ...)
# Read %output pane-id value lines from stdout
```

**Pros:**
- True real-time streaming with structured protocol
- Receives output from all panes simultaneously
- Full bidirectional tmux control (send commands, get responses)

**Cons:**
- Same fundamental problem as `pipe-pane`: output is raw terminal bytes (octal-escaped), not structured messages
- Complex protocol to implement (interleaved notifications and command responses)
- libtmux does not support control mode — requires raw subprocess management
- Output includes all TUI rendering, not just message content

---

### Option D: tmux `capture-pane` Polling (Current Approach)

Poll `pane.capture_pane()` on an interval and diff against previous snapshot.

**Pros:**
- Already implemented in the client
- Simple, no additional dependencies
- Can strip ANSI or get clean text

**Cons:**
- Polling-based — latency proportional to interval, can miss fast output
- Screen buffer is finite (scrollback limit) — long responses may be truncated
- Cannot distinguish event types (message vs tool output vs prompt)
- No semantic structure — just lines of text

---

## Comparison

| Criterion | A: Hooks | B: pipe-pane | C: Control Mode | D: capture-pane |
|-----------|----------|-------------|----------------|----------------|
| Structured events | Yes (JSON) | No (raw bytes) | No (raw bytes) | No (text lines) |
| Real-time | Yes (push) | Yes (push) | Yes (push) | No (polling) |
| Permission prompts | Yes (dedicated event) | Buried in TUI output | Buried in TUI output | Buried in TUI output |
| Tool call details | Yes (name, input, response) | No | No | No |
| Can block/allow actions | Yes (exit codes) | No | No | No |
| Assistant message text | Indirect (via transcript) | Requires ANSI parsing | Requires ANSI parsing | Requires ANSI parsing |
| Implementation complexity | Low | Medium | High | Low (exists) |
| Works across Docker bridge | Yes (hooks run on host) | Yes (if tmux accessible) | Yes (if tmux accessible) | Yes (current) |

## Recommendation

**Option A (Claude Code Hooks)** is the clear winner for structured event streaming. It is the only approach that provides semantic, structured data about what Claude is doing.

For assistant message text (the one gap in hook payloads), subscribers can read the `transcript_path` from the hook JSON if they need response text. The hook script itself does no enrichment -- it is a pure pass-through of the raw hook JSON.

The tmux-based approaches (B, C, D) all share the same fundamental limitation: Claude Code is a TUI application, and its raw terminal output is not designed to be machine-readable.

## Architecture

claude-code-hub is a single service with two internal data paths: a command path (create/message/stop) and an event path (hooks -> collector -> SSE).

```
                     ┌──────────────────────────────────────┐
                     │           claude-code-hub             │
                     │                                       │
 POST /sessions      │  ┌──────────────────────┐            │
 POST /sessions/     │  │   Session Manager     │            │
   {id}/message      │  │                       │            │
 DELETE /sessions/   │  │  - creates sessions   │            │
   {id}       ──────>│  │  - sends messages     │            │
                     │  │  - manages lifecycle   │            │
                     │  └──────┬───────────────┘            │
                     │         │                             │
                     │         │ start(--settings settings.json)
                     │         v                             │
                     │  ┌──────────────────────┐            │
                     │  │  ClaudeCodeClient(s)  │            │
                     │  │  (tmux sessions)      │            │
                     │  └──────┬───────────────┘            │
                     │         │                             │
                     │         │ hooks fire -> emit_event.py │
                     │         │ POST to collector_url/events│
                     │         v                             │
                     │  ┌──────────────────────┐            │
 GET /sessions/      │  │   Event Collector     │            │
   {id}/events  <───│  │   (POST /events in)   │            │
 (SSE stream)        │  │   (SSE streams out)   │            │
                     │  │                       │            │
                     │  │  - demux by session_id│            │
                     │  │  - per-session queues  │            │
                     │  └──────────────────────┘            │
                     │                                       │
                     └──────────────────────────────────────┘
```

### Components

**Session Manager** -- The public-facing API. Handles create session (requires `session_id`), post message, stop session, and subscribe to events. Owns `ClaudeCodeClient` instances.

**ClaudeCodeClient** -- Existing tmux wrapper. `__init__` requires `session_id` (not optional). The tmux session name is derived from it (e.g. `claude-{session_id[:8]}`). Enhanced to launch Claude with `--settings settings.json`. One instance per session.

**Event Collector** -- Internal HTTP server that receives `POST /events` from hook scripts and serves `GET /sessions/{id}/events` as SSE streams. Starts with the service, stops with the service. Routes events to per-session queues by `session_id` field in the payload. Returns 200 on successful receipt.

**`emit_event.py`** -- Hook script bundled in the repo. A pure JSON forwarder: reads hook JSON from stdin, POSTs it as-is to the collector. No parsing, no enrichment, no transformation. Runs on the host (not in Docker) where the repo is checked out. Uses `urllib.request` (stdlib) for zero external dependencies.

### Hook configuration

The project ships a static settings file (`src/claude_code_hub/hooks/settings.json`) with hook entries for **all 12 hook events**. `ClaudeCodeClient.start()` resolves the absolute path to `emit_event.py` at runtime and passes the settings file via `claude --settings <path>`.

The `--settings` flag **fully replaces** user settings. The bundled `settings.json` must include all settings the service needs: hooks configuration plus any other required settings (e.g. permission configuration).

Dynamic values (collector URL) are passed via environment variables set on the tmux pane. The hook command reads `CLAUDE_HUB_COLLECTOR_URL` at runtime.

No file generation, no mutation, no cleanup. The settings file is version-controlled and shared across all sessions.

**`settings.json` example:**
```json
{
  "permissions": {
    "allow": ["Read", "Write", "Bash"],
    "deny": []
  },
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "PreToolUse": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "PostToolUse": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "PostToolUseFailure": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "PermissionRequest": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "Notification": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "Stop": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "SubagentStart": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "SubagentStop": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "PreCompact": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }],
    "SessionEnd": [{ "hooks": [{ "type": "command", "command": "python3 /absolute/path/to/emit_event.py", "timeout": 10 }] }]
  }
}
```

> The absolute path to `emit_event.py` is resolved at runtime by `ClaudeCodeClient.start()` and injected into the hook commands before writing the effective settings file.

### Event Format

Events are **raw hook JSON pass-through**. The service defines no custom event schema. The event model is whatever Claude Code hooks provide.

Every hook event arrives as a JSON object on stdin with at least these common fields:

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/current/working/dir",
  "hook_event_name": "PostToolUse"
}
```

Plus event-specific fields (e.g. `tool_name`, `tool_input`, `tool_response` for `PostToolUse`).

The collector forwards this JSON verbatim to SSE subscribers. No fields are added, removed, or transformed. For `Stop` events specifically, the hook JSON does **not** include assistant message text -- subscribers that need the response text can read it from `transcript_path`.

### Subscribe API (SSE)

The service exposes an SSE (Server-Sent Events) endpoint per session:

```
GET /sessions/{session_id}/events
```

Subscribers connect via HTTP and receive a stream of JSON events. Each SSE message contains one hook event as raw JSON in the `data` field:

```
event: hook
data: {"session_id":"abc123","hook_event_name":"PostToolUse","tool_name":"Read","tool_input":{...},"tool_response":"...","transcript_path":"/...","cwd":"/..."}

event: hook
data: {"session_id":"abc123","hook_event_name":"Stop","stop_hook_active":true,"transcript_path":"/...","cwd":"/..."}
```

All 12 hook events are forwarded to subscribers. Subscribers filter client-side for the events they care about using the `hook_event_name` field.

### Session Lifecycle

1. **Create** -- `POST /sessions` with a required `session_id` in the request body. The API rejects requests without a `session_id`. The hub creates a `ClaudeCodeClient` with this ID. The tmux session name is derived from it (e.g. `claude-{session_id[:8]}`). The same `session_id` appears in all hook payloads from this session.

2. **Message** -- `POST /sessions/{session_id}/message` sends a prompt to the running session.

3. **Subscribe** -- `GET /sessions/{session_id}/events` opens an SSE stream. The subscriber receives all hook events for the session in near-real-time.

4. **Stop** -- `DELETE /sessions/{session_id}` stops the session. The `ClaudeCodeClient` kills the tmux session. A `SessionEnd` event fires and is forwarded to any active subscribers before the SSE stream closes.

### Event Ordering

Events may arrive out of order due to parallel hook execution (Claude Code runs all matching hooks in parallel). Each event includes `hook_event_name` to identify its type. The service provides **no server-side ordering guarantees** for v1. Subscribers must handle ordering if their use case requires it.

### Error handling in emit_event.py

The hook script is a fire-and-forget forwarder:
- If the POST to the collector fails (connection refused, timeout), log to stderr and exit 0. Never block Claude Code operation due to a collector issue.
- Set a short HTTP timeout (e.g. 2s) -- the collector is always localhost.
- Hook exit code is always 0 (allow). The hook never blocks tool execution.

### Graceful Shutdown

On hub shutdown, kill all managed tmux sessions: iterate `ClaudeCodeClient` instances and call `stop()` on each. On startup, do not attempt to reconnect to orphaned sessions. Clean shutdown means no orphans.

### Deployment Considerations

**Docker topology:** If the hub service runs in Docker and Claude Code runs on the host, `emit_event.py` (running on the host) needs to reach the collector endpoint inside the container. This requires a port mapping or bridge network (similar to the existing tmux socat bridge for the command path). The `CLAUDE_HUB_COLLECTOR_URL` env var must point to a host-accessible address (e.g. `http://host.docker.internal:{port}` or `http://localhost:{port}` with port mapping).

**`emit_event.py` on the host:** Since hooks run on the host where the repo is checked out, the script needs only Python (available on the host) and stdlib `urllib.request` (no pip install needed). The service itself (inside Docker or on the host) can use whatever HTTP framework is chosen.

## Decisions

1. **Service architecture.** claude-code-hub is a single service. The session manager, event collector, and client instances all live in one process. The collector starts/stops with the service.

2. **Transport: Internal HTTP.** The hook script POSTs JSON to `{collector_url}/events`. The URL is owned by the service and passed via env var. No external network involved.

3. **Packaging: Bundled in claude-code-hub.** The `emit_event.py` hook script and `settings.json` ship inside the package.

4. **Hook configuration: Static in-project settings file via `--settings` flag.** `--settings` fully replaces user settings. The bundled `settings.json` includes all settings the service needs (hooks config, permissions, etc.). `ClaudeCodeClient.start()` passes it via `claude --settings <path>`. Dynamic values via env vars.

5. **Per-session routing: Shared hooks, demux by `session_id`.** One settings file for all sessions. The hook script forwards `session_id` from the JSON payload. The collector routes to the correct per-session SSE stream.

6. **No transcript parsing.** `emit_event.py` is a pure JSON forwarder for all events including `Stop`. No enrichment, no transformation. Subscribers that need assistant message text can read `transcript_path` themselves.

7. **PermissionRequest: Notify only (v1).** The service forwards permission events to subscribers. Approval/denial happens in the terminal. Bidirectional approval via API is deferred.

8. **Error policy: Never block Claude.** Hook scripts always exit 0. HTTP failures are logged and dropped. Hook timeout set to 10s in `settings.json` to prevent hangs. `emit_event.py` uses a 2s HTTP timeout.

9. **Dependencies.** The hub service uses `aiohttp` or `starlette`+`uvicorn` for the HTTP/SSE server. `emit_event.py` uses stdlib `urllib.request` only -- zero external dependencies for the hook script since it runs on the host.

10. **Graceful shutdown.** On hub shutdown, iterate all `ClaudeCodeClient` instances and call `stop()` to kill managed tmux sessions. On startup, do not reconnect to orphaned sessions.

11. **Session ID required.** `ClaudeCodeClient.__init__` requires `session_id` (not optional). The create session API rejects requests without one. The tmux session name is derived from it. The same ID flows through hook payloads and SSE routing.

12. **Subscribe API: SSE.** The service exposes `GET /sessions/{session_id}/events` as an SSE endpoint. All 12 hook events are forwarded. Subscribers filter client-side.

13. **All events forwarded.** All 12 hook event types are configured in `settings.json` and forwarded to subscribers. No server-side filtering.
