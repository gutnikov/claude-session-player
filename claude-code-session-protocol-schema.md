# Claude Code Session Protocol Schema

> Reverse-engineered from Claude Code JSONL session files (v2.0.76 – v2.1.29).
> This document describes how Claude Code persists conversations as append-only JSONL logs,
> enabling you to build a compatible console client from scratch.

---

## Table of Contents

1. [Overview](#1-overview)
2. [File Layout & Naming](#2-file-layout--naming)
3. [Common Envelope Fields](#3-common-envelope-fields)
4. [Message Types Reference](#4-message-types-reference)
   - 4.1 [user](#41-user)
   - 4.2 [assistant](#42-assistant)
   - 4.3 [system](#43-system)
   - 4.4 [summary](#44-summary)
   - 4.5 [progress](#45-progress)
   - 4.6 [file-history-snapshot](#46-file-history-snapshot)
   - 4.7 [queue-operation](#47-queue-operation)
   - 4.8 [pr-link](#48-pr-link)
5. [Conversation Graph: The Parent Chain](#5-conversation-graph-the-parent-chain)
6. [Turn Lifecycle](#6-turn-lifecycle)
7. [Tool Use Protocol](#7-tool-use-protocol)
8. [Sub-Agent (Task) Protocol](#8-sub-agent-task-protocol)
9. [Context Compaction](#9-context-compaction)
10. [Streaming & Content Block Splitting](#10-streaming--content-block-splitting)
11. [Full Conversation Example](#11-full-conversation-example)
12. [Building a Client: Implementation Checklist](#12-building-a-client-implementation-checklist)

---

## 1. Overview

Claude Code persists every session as an **append-only JSONL file** (one JSON object per line).
The file is the single source of truth for conversation replay, undo, branching, and resumption.

Key design principles:

- **Append-only**: Lines are only appended, never modified or deleted.
- **DAG structure**: Each message has a `uuid` and a `parentUuid`, forming a directed acyclic graph (not a flat list). This enables branching, sidechains (sub-agents), and undo.
- **Per-content-block granularity**: Assistant responses are split into one JSONL line per content block (one for `text`, one per `tool_use`, one for `thinking`). This supports streaming display.
- **Tool results are user messages**: Following the Anthropic API convention, tool results are delivered as `role: "user"` messages with `type: "tool_result"` content blocks.

---

## 2. File Layout & Naming

```
~/.claude/projects/<project-slug>/
├── <uuid>.jsonl              # Main session files (UUID v4)
├── agent-<hex7>.jsonl        # Sub-agent session files
└── ...
```

| File Pattern               | Description                                                                               |
| -------------------------- | ----------------------------------------------------------------------------------------- |
| `<uuid>.jsonl`             | Primary conversation session. The UUID is the `sessionId`.                                |
| `agent-<7-char-hex>.jsonl` | Sub-agent (Task tool) session. Shares the parent's `sessionId` but has its own `agentId`. |

**Project slug** is derived from the working directory path with `/` replaced by `-`:

```
/Users/agutnikov/work/mtools → -Users-agutnikov-work-mtools
```

---

## 3. Common Envelope Fields

Most JSONL lines (except `file-history-snapshot` and `queue-operation`) share this envelope:

```jsonc
{
  // --- Identity ---
  "uuid": "c01b7ace-...",           // Unique ID of this message
  "parentUuid": "3ff42e6b-..." | null, // Parent in the conversation DAG
  "sessionId": "07c9cd52-...",      // Session file this belongs to
  "timestamp": "2026-01-03T15:44:58.325Z",

  // --- Message classification ---
  "type": "user" | "assistant" | "system" | "progress" | ...,
  "isSidechain": false,             // true for sub-agent messages
  "isMeta": false,                  // true for system-injected user messages (skill expansions)
  "userType": "external",           // Always "external" for local CLI

  // --- Context ---
  "cwd": "/Users/agutnikov/work/mtools",
  "version": "2.1.29",             // Claude Code version
  "gitBranch": "main",             // Current git branch at message time
  "slug": "virtual-puzzling-nygaard", // Human-readable session name (adjective-adjective-surname)

  // --- Sub-agent fields (only on agent sessions) ---
  "agentId": "a4c7249",            // 7-char hex agent ID
}
```

---

## 4. Message Types Reference

### 4.1 `user`

A message from the human user, a skill expansion, or a tool result.

#### 4.1.1 Direct User Input

```jsonc
{
  "type": "user",
  "parentUuid": null, // null for first message in session
  "uuid": "c01b7ace-...",
  "timestamp": "2026-01-03T15:44:58.325Z",
  "sessionId": "07c9cd52-...",
  "isMeta": false,
  "permissionMode": "default", // "default" | "plan" | other modes
  "message": {
    "role": "user",
    "content": "implement the backtest engine",
    // content can be a string OR an array of content blocks
  },
}
```

#### 4.1.2 Skill/Command Expansion (isMeta=true)

When the user invokes a slash command (e.g., `/implement-spec`), Claude Code injects an expanded prompt as a `user` message with `isMeta: true`. This message is the child of the original user message.

```jsonc
{
  "type": "user",
  "parentUuid": "c01b7ace-...", // Points to the raw command message
  "isMeta": true, // Marks this as system-injected
  "message": {
    "role": "user",
    "content": [
      {
        "type": "text",
        "text": "# Spec Implementation Workflow\n\nExecute the **Spec Implementation Workflow**...",
      },
    ],
  },
}
```

#### 4.1.3 Tool Result

After the assistant calls a tool, the result comes back as a `user` message containing `tool_result` blocks. There is **one JSONL line per tool result**, even if multiple tools were called in parallel.

```jsonc
{
  "type": "user",
  "parentUuid": "9cabbde7-...",     // Points to the assistant message that called the tool
  "isMeta": false,
  "message": {
    "role": "user",
    "content": [
      {
        "tool_use_id": "toolu_01DjYdxoudKLXxDoF7GwQWwB",
        "type": "tool_result",
        "content": "     1→# Spec Implementation Workflow\n     2→\n..."
        // content is a string (the tool output shown to the model)
      }
    ]
  },
  // --- Extra metadata (not sent to API, used by the UI) ---
  "toolUseResult": { ... }          // Structured result for UI rendering (see §7)
}
```

The `toolUseResult` field is **client-side metadata** not sent to the Anthropic API. It provides structured data for rendering (file paths, diffs, stdout/stderr, etc.).

---

### 4.2 `assistant`

A response from the Claude model. **Each content block is a separate JSONL line** sharing the same `requestId`.

#### 4.2.1 Text Block

```jsonc
{
  "type": "assistant",
  "parentUuid": "fb48eb31-...",
  "uuid": "8712c187-...",
  "requestId": "req_011CWkhijUz2iaH355mJPTAg",
  "message": {
    "model": "claude-opus-4-5-20251101",
    "id": "msg_011dxqU78CMCUZHFFbH6FFi7", // Anthropic message ID
    "type": "message",
    "role": "assistant",
    "content": [
      {
        "type": "text",
        "text": "I have the spec ticket. Let me proceed with implementation.",
      },
    ],
    "stop_reason": null, // null for non-final blocks; see §10
    "stop_sequence": null,
    "usage": {
      "input_tokens": 0,
      "cache_creation_input_tokens": 857,
      "cache_read_input_tokens": 36761,
      "cache_creation": {
        "ephemeral_5m_input_tokens": 857,
        "ephemeral_1h_input_tokens": 0,
      },
      "output_tokens": 1,
      "service_tier": "standard",
    },
  },
}
```

#### 4.2.2 Tool Use Block

```jsonc
{
  "type": "assistant",
  "parentUuid": "3ff42e6b-...",
  "uuid": "52527c90-...",
  "requestId": "req_011CWkhh93mAwD8862te1qrd",
  "message": {
    "model": "claude-opus-4-5-20251101",
    "id": "msg_01AA6xwBfNW41VdPgcGS3d7m",
    "type": "message",
    "role": "assistant",
    "content": [
      {
        "type": "tool_use",
        "id": "toolu_01DjYdxoudKLXxDoF7GwQWwB",
        "name": "Read",
        "input": {
          "file_path": "/Users/agutnikov/work/mtools/tickets/workflows/implement_spec.md"
        }
      }
    ],
    "stop_reason": null,            // null for intermediate blocks
    "stop_sequence": null,
    "usage": { ... }
  }
}
```

#### 4.2.3 Thinking Block

Extended thinking is recorded with a signature for verification:

```jsonc
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "thinking",
        "thinking": "The user wants me to continue. Let me launch a new cpp-developer agent...",
        "signature": "EpMCCkYICxgCKkDguxdb...", // Cryptographic signature
      },
    ],
    "stop_reason": null,
  },
}
```

---

### 4.3 `system`

System-level events. Distinguished by `subtype`.

#### 4.3.1 `compact_boundary` — Context Window Compaction

Emitted when the conversation is summarized to fit within context limits:

```jsonc
{
  "type": "system",
  "subtype": "compact_boundary",
  "parentUuid": null,
  "logicalParentUuid": "f842eacb-...", // The message this logically follows
  "content": "Conversation compacted",
  "isMeta": false,
  "level": "info",
  "compactMetadata": {
    "trigger": "auto", // "auto" or "manual" (/compact command)
    "preTokens": 167503, // Token count before compaction
  },
}
```

After a `compact_boundary`, a `summary` message (§4.4) typically precedes the next user message.

#### 4.3.2 `turn_duration` — Turn Timing

Emitted after each assistant turn completes:

```jsonc
{
  "type": "system",
  "subtype": "turn_duration",
  "parentUuid": "14ff661e-...",
  "durationMs": 88947,
  "isMeta": false,
}
```

#### 4.3.3 `local_command` — Slash Commands

Emitted when the user types a local slash command:

```jsonc
{
  "type": "system",
  "subtype": "local_command",
  "content": "<command-name>/agents</command-name>\n<command-message>agents</command-message>\n<command-args>create</command-args>",
  "level": "info",
  "isMeta": false,
}
```

---

### 4.4 `summary`

A compacted summary of prior conversation, used after context compaction or at session resumption:

```jsonc
{
  "type": "summary",
  "summary": "Backtest engine implementation spec workflow",
  "leafUuid": "7777775b-...", // UUID of the last message before compaction
}
```

Multiple `summary` entries can exist in a file (each compaction adds one).

---

### 4.5 `progress`

Real-time progress events for long-running operations. Not part of the conversation graph — used purely for UI updates.

#### 4.5.1 `bash_progress` — Shell Command Output

```jsonc
{
  "type": "progress",
  "data": {
    "type": "bash_progress",
    "output": "Step 1/12 : FROM python:3.11-slim\n...", // Incremental stdout
    "fullOutput": "DEPRECATED: The legacy builder is...", // Complete output so far
  },
  "toolUseID": "toolu_015hQa...",
  "parentToolUseID": "toolu_015hQa...",
}
```

#### 4.5.2 `agent_progress` — Sub-Agent Activity

```jsonc
{
  "type": "progress",
  "data": {
    "type": "agent_progress",
    "message": {
      "type": "user",
      "message": {
        "role": "user",
        "content": [{ "type": "text", "text": "Explore this codebase..." }],
      },
    },
  },
  "toolUseID": "...",
  "parentToolUseID": "toolu_...",
}
```

#### 4.5.3 `hook_progress` — Hook Execution

```jsonc
{
  "type": "progress",
  "data": {
    "type": "hook_progress",
    "hookEvent": "SessionStart",
    "hookName": "SessionStart:startup",
    "command": "echo hello-from-hook",
  },
}
```

#### 4.5.4 `query_update` / `search_results_received` — Web Search

```jsonc
// Search initiated
{
  "type": "progress",
  "data": { "type": "query_update", "query": "Claude Code hooks feature 2026" }
}

// Results received
{
  "type": "progress",
  "data": { "type": "search_results_received", "resultCount": 10, "query": "..." }
}
```

#### 4.5.5 `waiting_for_task` — Background Task

```jsonc
{
  "type": "progress",
  "data": {
    "type": "waiting_for_task",
    "taskDescription": "Debug socat bridge from inside Docker container",
    "taskType": "local_bash",
  },
}
```

---

### 4.6 `file-history-snapshot`

Tracks file states for undo/restore. Appears before and after file-modifying operations.

```jsonc
// Initial snapshot (before modifications)
{
  "type": "file-history-snapshot",
  "messageId": "c01b7ace-...",         // Links to the user message that triggered it
  "snapshot": {
    "messageId": "c01b7ace-...",
    "trackedFileBackups": {},          // Empty = no files tracked yet
    "timestamp": "2026-01-03T15:44:58.335Z"
  },
  "isSnapshotUpdate": false
}

// Update snapshot (after modifications)
{
  "type": "file-history-snapshot",
  "messageId": "1f442222-...",
  "snapshot": {
    "messageId": "78d94c7b-...",
    "trackedFileBackups": {
      "tickets/discussions/003_backtest-engine/2026-01-03_implementation.md": "<original file content>"
    },
    "timestamp": "2026-01-03T22:40:42.028Z"
  },
  "isSnapshotUpdate": true
}
```

---

### 4.7 `queue-operation`

Session queue management (e.g., when messages arrive while the model is busy):

```jsonc
{
  "type": "queue-operation",
  "operation": "dequeue",
  "timestamp": "2026-02-02T12:57:40.217Z",
  "sessionId": "37dfb8a0-...",
}
```

---

### 4.8 `pr-link`

Emitted when a PR is created during the session:

```jsonc
{
  "type": "pr-link",
  "sessionId": "adebd821-...",
  "prNumber": 3,
  "prUrl": "https://github.com/gutnikov/claude-code-hub/pull/3",
  "prRepository": "gutnikov/claude-code-hub",
  "timestamp": "2026-02-02T17:09:00.881Z",
}
```

---

## 5. Conversation Graph: The Parent Chain

Messages form a **linked list** (or tree for branches) via `parentUuid` → `uuid`:

```
null
 └─► user (uuid=A, parentUuid=null)      "implement-spec"
      └─► user (uuid=B, parentUuid=A)     isMeta=true, skill expansion
           └─► assistant (uuid=C, parentUuid=B)   tool_use: Read
                └─► assistant (uuid=D, parentUuid=C)   tool_use: Glob
                     └─► user (uuid=E, parentUuid=D)    tool_result for Read
                          └─► user (uuid=F, parentUuid=E)  tool_result for Glob
                               └─► assistant (uuid=G, parentUuid=F)   text response
```

**Rules**:

1. The first user message in a session has `parentUuid: null`.
2. Each subsequent message points to the previous message as its parent.
3. Assistant content blocks are chained: each block's `parentUuid` points to the previous block (not to the user message that started the turn).
4. Tool results point to the last assistant content block.
5. Multiple tool results (from parallel tool calls) form a chain among themselves.
6. Sub-agent messages have `isSidechain: true` and share the parent session's `sessionId`.

---

## 6. Turn Lifecycle

A "turn" is one cycle of: user message → model response → tool execution → model continues.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TURN LIFECYCLE                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. User types message                                              │
│     → Write `user` JSONL line                                       │
│     → Write `file-history-snapshot` (isSnapshotUpdate=false)        │
│                                                                     │
│  2. (Optional) Skill expansion                                      │
│     → Write `user` JSONL line with isMeta=true                      │
│                                                                     │
│  3. Send to Anthropic API                                           │
│     → Receive streaming response                                    │
│                                                                     │
│  4. For each content block in the response:                         │
│     → Write `assistant` JSONL line                                  │
│     → If `thinking`: record thinking text + signature               │
│     → If `text`: display to user                                    │
│     → If `tool_use`: prepare to execute tool                        │
│                                                                     │
│  5. If stop_reason == "tool_use":                                   │
│     → Execute each tool                                             │
│     → Write `progress` lines during execution (bash_progress, etc.) │
│     → Write `user` JSONL line with tool_result for each tool        │
│     → Write `file-history-snapshot` if files were modified          │
│     → Go to step 3 (next API call with tool results)                │
│                                                                     │
│  6. If stop_reason == "end_turn" or null (final text):              │
│     → Turn is complete                                              │
│     → Write `system` with subtype=turn_duration                     │
│     → Wait for next user input                                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 7. Tool Use Protocol

### 7.1 Tool Invocation (Assistant → Tool)

The assistant emits a `tool_use` content block:

```jsonc
{
  "type": "tool_use",
  "id": "toolu_01DjYdxoudKLXxDoF7GwQWwB", // Unique tool use ID
  "name": "Read", // Tool name
  "input": {
    // Tool-specific parameters
    "file_path": "/path/to/file.md",
  },
}
```

### 7.2 Tool Result (Tool → Model)

The client executes the tool and returns the result as a `user` message:

```jsonc
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "toolu_01DjYdxoudKLXxDoF7GwQWwB", // Matches the tool_use.id
        "content": "<tool output as string>",
      },
    ],
  },
}
```

### 7.3 `toolUseResult` Metadata

Each tool result message also has a `toolUseResult` field with structured data for UI rendering. This field is **not** sent to the Anthropic API.

#### Read Tool

```jsonc
"toolUseResult": {
  "type": "text",
  "file": {
    "filePath": "/path/to/file.md",
    "content": "<full file content>",
    "numLines": 473,
    "startLine": 1,
    "totalLines": 473
  }
}
```

#### Glob Tool

```jsonc
"toolUseResult": {
  "filenames": ["/path/to/match1.cpp", "/path/to/match2.cpp"],
  "durationMs": 128,
  "numFiles": 2,
  "truncated": false
}
```

#### Bash Tool

```jsonc
"toolUseResult": {
  "stdout": "M apps/collector/main.cpp\nM include/mtools/...",
  "stderr": "",
  "interrupted": false,
  "isImage": false
}
```

#### Write Tool

```jsonc
"toolUseResult": {
  "type": "create",                // "create" for new file, "update" for existing
  "filePath": "/path/to/new-file.md",
  "content": "<full written content>",
  "structuredPatch": [],           // Empty for new files
  "originalFile": null             // null for new files
}
```

#### Edit Tool

```jsonc
"toolUseResult": {
  "filePath": "/path/to/file.md",
  "oldString": "| **Status** | Decided |",
  "newString": "| **Status** | Implemented |",
  "originalFile": "<full original file content>",
  "structuredPatch": [
    {
      "oldStart": 4,
      "oldLines": 7,
      "newStart": 4,
      "newLines": 7,
      "lines": [
        " |-------|-------|",
        "-| **Status** | Decided |",
        "+| **Status** | Implemented |",
        " | **Created** | 2026-01-03 |"
      ]
    }
  ],
  "userModified": false,           // true if user edited the change before accepting
  "replaceAll": false
}
```

#### TodoWrite Tool

```jsonc
"toolUseResult": {
  "oldTodos": [],
  "newTodos": [
    {
      "content": "Phase 1: Setup & Initialization",
      "status": "in_progress",
      "activeForm": "Setting up and initializing workflow"
    },
    {
      "content": "Phase 2: Input Parsing & Validation",
      "status": "pending",
      "activeForm": "Parsing and validating inputs"
    }
  ]
}
```

#### Task (Sub-Agent) Tool

```jsonc
"toolUseResult": {
  "status": "completed",
  "prompt": "Implement the following feature...",
  "agentId": "ab97f57",
  "content": [
    {
      "type": "text",
      "text": "There are still 114 errors. Given the extensive scope..."
    }
  ],
  "totalDurationMs": 785728,
  "totalTokens": 126186,
  "totalToolUseCount": 77,
  "usage": {
    "input_tokens": 1,
    "cache_creation_input_tokens": 191,
    "cache_read_input_tokens": 125212,
    "output_tokens": 782,
    "service_tier": "standard"
  }
}
```

---

## 8. Sub-Agent (Task) Protocol

When the assistant calls the `Task` tool, Claude Code spawns a sub-agent:

1. **Parent session** writes an `assistant` message with `tool_use` for `Task`.
2. Claude Code creates a new file `agent-<agentId>.jsonl`.
3. The sub-agent's first message is a `user` message with:
   - `isSidechain: true`
   - `agentId: "<7-char-hex>"`
   - `sessionId`: **same as parent** session
   - `parentUuid: null` (root of this sidechain)
4. The sub-agent runs autonomously (its own tool calls and results logged to its own file).
5. When complete, the parent session receives a `tool_result` with the sub-agent's final output.
6. The parent's `toolUseResult` contains `agentId`, `status`, `content`, and usage stats.

```
Parent session (07c9cd52.jsonl)          Agent session (agent-ab97f57.jsonl)
┌──────────────────────────┐             ┌──────────────────────────┐
│ assistant: tool_use Task │────spawn───►│ user: "Implement..."     │
│ (toolu_01...)            │             │   isSidechain: true      │
│                          │             │   agentId: "ab97f57"     │
│                          │             ├──────────────────────────┤
│                          │             │ assistant: tool_use Read │
│                          │             │ user: tool_result        │
│                          │             │ assistant: tool_use Edit │
│                          │             │ user: tool_result        │
│                          │             │ assistant: text (final)  │
│                          │◄──result────│                          │
├──────────────────────────┤             └──────────────────────────┘
│ user: tool_result        │
│   toolUseResult.agentId  │
│   = "ab97f57"            │
└──────────────────────────┘
```

---

## 9. Context Compaction

When the conversation exceeds the context window, Claude Code compacts it:

1. A `summary` line is written with a text summary and `leafUuid` pointing to the last pre-compaction message.
2. A `system` line with `subtype: "compact_boundary"` marks the boundary.
   - `compactMetadata.trigger`: `"auto"` or `"manual"` (user ran `/compact`)
   - `compactMetadata.preTokens`: token count before compaction
   - `logicalParentUuid`: the logical predecessor message
   - `parentUuid: null`: resets the parent chain (new conversation root)
3. Subsequent messages continue from this new root.

```
... (many messages, ~167k tokens) ...
{"type": "summary", "summary": "Code audit fixes...", "leafUuid": "eee48666-..."}
{"type": "system", "subtype": "compact_boundary", "parentUuid": null,
 "logicalParentUuid": "f842eacb-...", "compactMetadata": {"trigger": "auto", "preTokens": 167503}}
{"type": "user", "parentUuid": null, ...}   // Conversation continues with fresh context
```

---

## 10. Streaming & Content Block Splitting

Claude Code splits each assistant API response into **one JSONL line per content block**.

For a single API call that returns `[thinking, text, tool_use, tool_use]`, you get **4 JSONL lines**, all sharing the same `requestId` and Anthropic `message.id`.

```
Line 1: { type: "assistant", requestId: "req_X", message.content: [{ type: "thinking", ... }], stop_reason: null }
Line 2: { type: "assistant", requestId: "req_X", message.content: [{ type: "text", ... }],     stop_reason: null }
Line 3: { type: "assistant", requestId: "req_X", message.content: [{ type: "tool_use", ... }],  stop_reason: null }
Line 4: { type: "assistant", requestId: "req_X", message.content: [{ type: "tool_use", ... }],  stop_reason: "tool_use" }
```

**`stop_reason` values**:
| Value | Meaning |
|---|---|
| `null` | Intermediate content block (more blocks to come or streaming not finalized) |
| `"tool_use"` | Final block of a response that requires tool execution |
| `"end_turn"` | Final block, conversation turn is complete |
| `"stop_sequence"` | Model hit a stop sequence |

To reconstruct the full API message for replay, group consecutive `assistant` lines by `requestId` and concatenate their `content` arrays.

---

## 11. Full Conversation Example

Here is a minimal but complete session showing the JSONL lines for a simple interaction:

```jsonl
{"type":"file-history-snapshot","messageId":"aaa-111","snapshot":{"messageId":"aaa-111","trackedFileBackups":{},"timestamp":"2026-01-03T10:00:00.000Z"},"isSnapshotUpdate":false}
{"type":"user","parentUuid":null,"sessionId":"sess-001","uuid":"aaa-111","timestamp":"2026-01-03T10:00:00.000Z","isSidechain":false,"isMeta":false,"userType":"external","cwd":"/home/user/project","version":"2.1.29","gitBranch":"main","message":{"role":"user","content":"Read the README and tell me what this project does"}}
{"type":"assistant","parentUuid":"aaa-111","sessionId":"sess-001","uuid":"bbb-222","timestamp":"2026-01-03T10:00:02.000Z","requestId":"req_001","isSidechain":false,"userType":"external","cwd":"/home/user/project","version":"2.1.29","gitBranch":"main","message":{"model":"claude-opus-4-5-20251101","id":"msg_001","type":"message","role":"assistant","content":[{"type":"tool_use","id":"toolu_001","name":"Read","input":{"file_path":"/home/user/project/README.md"}}],"stop_reason":"tool_use","stop_sequence":null,"usage":{"input_tokens":500,"output_tokens":50}}}
{"type":"user","parentUuid":"bbb-222","sessionId":"sess-001","uuid":"ccc-333","timestamp":"2026-01-03T10:00:03.000Z","isSidechain":false,"isMeta":false,"userType":"external","cwd":"/home/user/project","version":"2.1.29","gitBranch":"main","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_001","content":"# My Project\n\nA CLI tool for managing widgets."}]},"toolUseResult":{"type":"text","file":{"filePath":"/home/user/project/README.md","content":"# My Project\n\nA CLI tool for managing widgets.","numLines":3,"startLine":1,"totalLines":3}}}
{"type":"assistant","parentUuid":"ccc-333","sessionId":"sess-001","uuid":"ddd-444","timestamp":"2026-01-03T10:00:05.000Z","requestId":"req_002","isSidechain":false,"userType":"external","cwd":"/home/user/project","version":"2.1.29","gitBranch":"main","message":{"model":"claude-opus-4-5-20251101","id":"msg_002","type":"message","role":"assistant","content":[{"type":"text","text":"This project is a CLI tool for managing widgets."}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":600,"output_tokens":20}}}
{"type":"system","parentUuid":"ddd-444","sessionId":"sess-001","uuid":"eee-555","timestamp":"2026-01-03T10:00:05.500Z","subtype":"turn_duration","durationMs":5500,"isMeta":false,"isSidechain":false,"userType":"external","cwd":"/home/user/project","version":"2.1.29","gitBranch":"main"}
```

---

## 12. Building a Client: Implementation Checklist

### 12.1 Session Management

- [ ] Generate UUID v4 for each new session
- [ ] Create JSONL file at `~/.claude/projects/<project-slug>/<session-id>.jsonl`
- [ ] Derive project slug from `cwd` (replace `/` with `-`, strip leading `-`)
- [ ] Generate a human-readable slug (adjective-adjective-surname pattern) for `slug` field
- [ ] Track `cwd`, `gitBranch`, `version` for each message

### 12.2 Message Writing

- [ ] Append each message as a single JSON line (no pretty-printing)
- [ ] Generate UUID for each message
- [ ] Set `parentUuid` to the previous message's UUID (null for first)
- [ ] Write `file-history-snapshot` before/after file modifications
- [ ] Include `timestamp` in ISO 8601 format

### 12.3 API Integration

- [ ] Send messages with `role: "user"` and `role: "assistant"` to the Anthropic Messages API
- [ ] Include tool definitions in the API request
- [ ] Handle streaming responses: split each content block into a separate JSONL line
- [ ] Track `requestId` across content blocks from the same API call
- [ ] Handle `stop_reason` to determine if tools need execution

### 12.4 Tool Execution

- [ ] Parse `tool_use` content blocks from assistant responses
- [ ] Execute tools locally (Read, Write, Edit, Bash, Glob, Grep, etc.)
- [ ] Format results as `tool_result` content blocks in `user` messages
- [ ] Include `toolUseResult` metadata for UI rendering
- [ ] Handle parallel tool calls (multiple `tool_use` blocks in one response)

### 12.5 Sub-Agent Support

- [ ] When `Task` tool is called, create `agent-<hex>.jsonl` file
- [ ] Run sub-agent with its own conversation loop (recursive)
- [ ] Set `isSidechain: true` and `agentId` on sub-agent messages
- [ ] Return sub-agent result as `tool_result` in parent session
- [ ] Track sub-agent `totalDurationMs`, `totalTokens`, `totalToolUseCount`

### 12.6 Context Management

- [ ] Track token usage from API responses
- [ ] Implement compaction: summarize conversation when approaching context limit
- [ ] Write `summary` and `system` (compact_boundary) messages
- [ ] Reset `parentUuid` to null after compaction

### 12.7 Progress Reporting

- [ ] Emit `progress` messages for bash output streaming
- [ ] Emit `progress` messages for sub-agent activity
- [ ] Emit `progress` messages for hooks execution
- [ ] Emit `system` with `turn_duration` after each turn

### 12.8 Session Resumption

- [ ] Read existing JSONL file to reconstruct conversation
- [ ] Build the parent chain (DAG) from `uuid`/`parentUuid`
- [ ] Find the leaf message (latest in the chain)
- [ ] Reconstruct API messages by grouping assistant blocks by `requestId`
- [ ] If compacted: start from the `summary` + `compact_boundary` messages

---

## Appendix A: Complete Field Reference

### User Message Fields

| Field             | Type              | Required | Description                               |
| ----------------- | ----------------- | -------- | ----------------------------------------- |
| `type`            | `"user"`          | yes      | Message type                              |
| `uuid`            | string            | yes      | Unique message identifier                 |
| `parentUuid`      | string \| null    | yes      | Parent message UUID                       |
| `sessionId`       | string            | yes      | Session identifier                        |
| `timestamp`       | string (ISO 8601) | yes      | Creation time                             |
| `message`         | object            | yes      | API message payload                       |
| `message.role`    | `"user"`          | yes      | Always "user"                             |
| `message.content` | string \| array   | yes      | Text string or array of content blocks    |
| `isSidechain`     | boolean           | yes      | true if sub-agent message                 |
| `isMeta`          | boolean           | no       | true if system-injected (skill expansion) |
| `userType`        | `"external"`      | yes      | Always "external"                         |
| `cwd`             | string            | yes      | Working directory                         |
| `version`         | string            | yes      | Claude Code version                       |
| `gitBranch`       | string            | no       | Current git branch                        |
| `slug`            | string            | no       | Human-readable session name               |
| `agentId`         | string            | no       | Sub-agent ID (7-char hex)                 |
| `permissionMode`  | string            | no       | Permission mode ("default", etc.)         |
| `toolUseResult`   | object            | no       | Structured tool result for UI             |

### Assistant Message Fields

| Field                 | Type              | Required | Description                                   |
| --------------------- | ----------------- | -------- | --------------------------------------------- |
| `type`                | `"assistant"`     | yes      | Message type                                  |
| `uuid`                | string            | yes      | Unique message identifier                     |
| `parentUuid`          | string            | yes      | Parent message UUID                           |
| `sessionId`           | string            | yes      | Session identifier                            |
| `timestamp`           | string (ISO 8601) | yes      | Creation time                                 |
| `requestId`           | string            | yes      | Groups content blocks from same API call      |
| `message`             | object            | yes      | Full Anthropic API response payload           |
| `message.model`       | string            | yes      | Model identifier                              |
| `message.id`          | string            | yes      | Anthropic message ID                          |
| `message.role`        | `"assistant"`     | yes      | Always "assistant"                            |
| `message.content`     | array             | yes      | Single content block per JSONL line           |
| `message.stop_reason` | string \| null    | yes      | null, "tool_use", "end_turn", "stop_sequence" |
| `message.usage`       | object            | yes      | Token usage statistics                        |

### Content Block Types

| Type          | Fields                   | Description           |
| ------------- | ------------------------ | --------------------- |
| `text`        | `text`                   | Plain text response   |
| `tool_use`    | `id`, `name`, `input`    | Tool invocation       |
| `tool_result` | `tool_use_id`, `content` | Tool execution result |
| `thinking`    | `thinking`, `signature`  | Extended thinking     |

---

## Appendix B: Known Tool Names

Tools observed in session logs:

| Tool        | Description                      | Input Keys                                              |
| ----------- | -------------------------------- | ------------------------------------------------------- |
| `Read`      | Read a file                      | `file_path`, `offset?`, `limit?`                        |
| `Write`     | Write/create a file              | `file_path`, `content`                                  |
| `Edit`      | Edit a file (string replacement) | `file_path`, `old_string`, `new_string`, `replace_all?` |
| `Bash`      | Execute shell command            | `command`, `description?`, `timeout?`                   |
| `Glob`      | Find files by pattern            | `pattern`, `path?`                                      |
| `Grep`      | Search file contents             | `pattern`, `path?`, `glob?`, `output_mode?`             |
| `Task`      | Launch sub-agent                 | `description`, `subagent_type`, `prompt`, `model?`      |
| `TodoWrite` | Write todo list                  | `todos` (array of {content, status, activeForm})        |
| `WebSearch` | Search the web                   | `query`                                                 |
| `WebFetch`  | Fetch URL content                | `url`, `prompt`                                         |

---

## Appendix C: Reconstructing API Messages from JSONL

To replay a session or send the conversation to the Anthropic API:

```python
import json

def load_session(jsonl_path):
    """Load a JSONL session and reconstruct API messages."""
    messages = []

    with open(jsonl_path) as f:
        for line in f:
            entry = json.loads(line)

            if entry["type"] == "user" and not entry.get("isMeta"):
                messages.append(entry["message"])

            elif entry["type"] == "assistant":
                # Group by requestId - merge content blocks
                if (messages and
                    messages[-1].get("role") == "assistant" and
                    messages[-1].get("_requestId") == entry.get("requestId")):
                    # Append content block to existing message
                    messages[-1]["content"].extend(entry["message"]["content"])
                else:
                    # New assistant message
                    msg = {
                        "role": "assistant",
                        "content": list(entry["message"]["content"]),
                        "_requestId": entry.get("requestId")  # tracking only
                    }
                    messages.append(msg)

            elif entry["type"] == "summary":
                # After compaction, prepend summary as context
                messages = [{
                    "role": "user",
                    "content": f"[Previous conversation summary]: {entry['summary']}"
                }]

    # Clean up tracking fields
    for msg in messages:
        msg.pop("_requestId", None)

    return messages
```

---

_Generated by analyzing Claude Code session files (v2.0.76 – v2.1.29), January–February 2026._
