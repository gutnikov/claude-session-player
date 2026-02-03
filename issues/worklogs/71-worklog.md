# Issue #71: Add TelegramPublisher for Telegram Bot API integration

## Summary

Implemented `TelegramPublisher` class for sending and updating messages via the Telegram Bot API using the aiogram library. This includes custom exceptions, message formatting utilities, and graceful handling when aiogram is not installed.

## Changes Made

### New Files

1. **`claude_session_player/watcher/telegram_publisher.py`**
   - `TelegramError`: Base exception for Telegram operations
   - `TelegramAuthError`: Bot authentication/validation failed exception
   - `ToolCallInfo`: Dataclass for tool call information in message formatting
   - `escape_markdown()`: Escapes special characters for Telegram Markdown
   - `get_tool_icon()`: Returns emoji icon for tool names
   - `format_user_message()`: Formats user messages for Telegram
   - `format_turn_message()`: Formats complete turn messages (assistant + tools + duration)
   - `format_system_message()`: Formats system messages
   - `format_context_compacted()`: Returns context compaction notice
   - `_truncate_message()`: Truncates messages to 4096 char limit
   - `TelegramPublisher` class with:
     - `__init__(token)`: Initialize with optional bot token
     - `validate()`: Validate bot credentials via `get_me()`
     - `send_message()`: Send new message with retry and truncation
     - `edit_message()`: Edit existing message with retry and "not modified" handling
     - `close()`: Close bot session

2. **`tests/watcher/test_telegram_publisher.py`**
   - 55 tests covering all functionality
   - Uses `make_telegram_api_error()` helper for creating aiogram exceptions

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added exports for all new classes and functions
   - Updated `__all__` list with 10 new exports

## Design Decisions

### Markdown Escaping Strategy

Using Telegram Markdown V1 style escaping which requires escaping: `_`, `*`, `` ` ``, `[`. The `escape_markdown()` function uses a compiled regex for efficiency.

### Error Handling

- `TelegramError` is the base exception for all Telegram operations
- `TelegramAuthError` specifically indicates authentication failures
- Both `send_message()` and `edit_message()` retry once on API failure before giving up
- `edit_message()` returns `True` for "message is not modified" errors (content unchanged is fine)
- `edit_message()` returns `False` for "message to edit not found" errors

### Message Truncation

Messages are truncated to 4076 characters (4096 - 20 for truncation indicator) to fit Telegram's message length limit. The truncation indicator `\n\n... [truncated]` is appended.

### Graceful Dependency Handling

If aiogram is not installed, `validate()` raises `TelegramError` with a helpful message. This is checked using `check_telegram_available()` from `deps.py`.

### Tool Icons

Added emoji icons for common tools:
- Read: 📖
- Write: 📝
- Edit: ✏️
- Bash: 🔧
- Glob/Grep: 🔍
- Task: 🤖
- WebSearch/WebFetch: 🌐
- Unknown: ⚙️

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestEscapeMarkdown | 7 | markdown escaping |
| TestGetToolIcon | 6 | tool icon mapping |
| TestFormatUserMessage | 3 | user message formatting |
| TestFormatTurnMessage | 7 | turn message formatting |
| TestFormatSystemMessage | 2 | system message formatting |
| TestFormatContextCompacted | 1 | compaction notice |
| TestTruncateMessage | 4 | message truncation |
| TestTelegramPublisherInit | 2 | initialization |
| TestTelegramPublisherValidate | 5 | validation |
| TestTelegramPublisherSendMessage | 5 | send message |
| TestTelegramPublisherEditMessage | 6 | edit message |
| TestTelegramPublisherClose | 2 | close session |
| TestModuleImports | 5 | package imports |

## Test Results

- **Before:** 912 tests
- **After:** 967 tests (55 new)
- All tests pass

## Acceptance Criteria Status

- [x] `TelegramPublisher` class in `claude_session_player/watcher/telegram_publisher.py`
- [x] `validate()` checks token and calls `get_me()`
- [x] `send_message()` sends with retry, respects 4096 char limit
- [x] `edit_message()` edits with retry, handles "not modified" gracefully
- [x] Custom exceptions: `TelegramError`, `TelegramAuthError`
- [x] Formatting utilities for user/turn/system messages
- [x] Markdown escaping for user content
- [x] `close()` properly shuts down bot session
- [x] Unit tests with mocked aiogram:
  - [x] Validation success/failure
  - [x] Send message success
  - [x] Send message with retry
  - [x] Send message truncation
  - [x] Edit message success
  - [x] Edit message "not modified" handling
  - [x] Message formatting
- [x] Graceful handling when aiogram not installed

## Spec Reference

Implements issue #71 from `.claude/specs/messaging-integration.md`:
- TelegramPublisher component for Telegram Bot API integration
- Message sending and editing with retry logic
- Message formatting utilities for Telegram Markdown
