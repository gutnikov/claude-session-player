# Issue #72: Add SlackPublisher for Slack Web API integration

## Summary

Implemented `SlackPublisher` class for sending and updating messages via the Slack Web API using the slack-sdk library. This includes custom exceptions, Block Kit message formatting utilities, and graceful handling when slack-sdk is not installed.

## Changes Made

### New Files

1. **`claude_session_player/watcher/slack_publisher.py`**
   - `SlackError`: Base exception for Slack operations
   - `SlackAuthError`: Bot authentication/validation failed exception
   - `ToolCallInfo`: Dataclass for tool call information in message formatting
   - `escape_mrkdwn()`: Escapes special characters for Slack mrkdwn (&, <, >)
   - `get_tool_icon()`: Returns emoji icon for tool names
   - `format_user_message_blocks()`: Formats user messages as Block Kit blocks
   - `format_turn_message_blocks()`: Formats complete turn messages (assistant + tools + duration)
   - `format_system_message_blocks()`: Formats system messages as Block Kit blocks
   - `format_context_compacted_blocks()`: Returns context compaction notice as blocks
   - `_truncate_blocks()`: Truncates blocks list to 50 block limit
   - `SlackPublisher` class with:
     - `__init__(token)`: Initialize with optional bot token
     - `validate()`: Validate bot credentials via `auth_test()`
     - `send_message()`: Post new message with retry and block truncation
     - `update_message()`: Update existing message with retry and "not found" handling
     - `close()`: Close client session

2. **`tests/watcher/test_slack_publisher.py`**
   - 57 tests covering all functionality
   - Uses `make_slack_api_error()` helper for creating slack-sdk exceptions

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added imports for all new classes and functions from slack_publisher
   - Updated `__all__` list with 11 new exports:
     - `SlackAuthError`, `SlackError`, `SlackPublisher`
     - `SlackToolCallInfo`, `slack_get_tool_icon`
     - `escape_mrkdwn`
     - `format_user_message_blocks`, `format_turn_message_blocks`
     - `format_system_message_blocks`, `format_context_compacted_blocks`

## Design Decisions

### mrkdwn Escaping Strategy

Slack uses a different escaping scheme than Telegram. For mrkdwn, only `&`, `<`, and `>` need to be escaped:
- `&` → `&amp;`
- `<` → `&lt;`
- `>` → `&gt;`

The order matters: ampersand is escaped first to avoid double-escaping.

### Error Handling

- `SlackError` is the base exception for all Slack operations
- `SlackAuthError` specifically indicates authentication failures
- Both `send_message()` and `update_message()` retry once on API failure before giving up
- `update_message()` returns `False` for "message_not_found" errors

### Block Kit Truncation

Messages are truncated to 50 blocks (Slack's limit). When truncation is needed:
- Keep first 49 blocks
- Add a truncation indicator block at the end

### Tool Result Truncation

Tool results in Block Kit are truncated to 1000 characters (vs 500 for Telegram) since Slack has a higher character limit per block.

### Graceful Dependency Handling

If slack-sdk is not installed, `validate()` raises `SlackError` with a helpful message. This is checked using `check_slack_available()` from `deps.py`.

### Tool Icons

Uses the same emoji icons as TelegramPublisher for consistency:
- Read: 📖, Write: 📝, Edit: ✏️, Bash: 🔧
- Glob/Grep: 🔍, Task: 🤖, WebSearch/WebFetch: 🌐
- Unknown: ⚙️

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestEscapeMrkdwn | 7 | mrkdwn escaping |
| TestGetToolIcon | 6 | tool icon mapping |
| TestFormatUserMessageBlocks | 3 | user message formatting |
| TestFormatTurnMessageBlocks | 7 | turn message formatting |
| TestFormatSystemMessageBlocks | 2 | system message formatting |
| TestFormatContextCompactedBlocks | 1 | compaction notice |
| TestTruncateBlocks | 4 | block truncation |
| TestSlackPublisherInit | 2 | initialization |
| TestSlackPublisherValidate | 6 | validation |
| TestSlackPublisherSendMessage | 6 | send message |
| TestSlackPublisherUpdateMessage | 6 | update message |
| TestSlackPublisherClose | 2 | close session |
| TestModuleImports | 5 | package imports |

## Test Results

- **Before:** 967 tests
- **After:** 1024 tests (57 new)
- All tests pass

## Acceptance Criteria Status

- [x] `SlackPublisher` class in `claude_session_player/watcher/slack_publisher.py`
- [x] `validate()` checks token and calls `auth_test()`
- [x] `send_message()` posts with retry, respects 50 block limit
- [x] `update_message()` updates with retry, handles "message_not_found"
- [x] Custom exceptions: `SlackError`, `SlackAuthError`
- [x] Block Kit formatting utilities for user/turn/system messages
- [x] mrkdwn escaping for user content
- [x] `close()` properly shuts down client session
- [x] Unit tests with mocked slack-sdk:
  - [x] Validation success/failure
  - [x] Post message success
  - [x] Post message with retry
  - [x] Block limit enforcement
  - [x] Update message success
  - [x] Update message "not found" handling
  - [x] Block Kit formatting
- [x] Graceful handling when slack-sdk not installed

## Spec Reference

Implements issue #72 from `.claude/specs/messaging-integration.md`:
- SlackPublisher component for Slack Web API integration
- Message sending and updating with retry logic
- Block Kit formatting utilities for rich message formatting
