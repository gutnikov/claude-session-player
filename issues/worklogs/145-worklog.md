# Issue #145: Telegram supergroup topic support

## Summary

Added support for Telegram supergroup topics (forums), allowing each topic to receive a dedicated Claude session stream. This feature uses the `message_thread_id` parameter in the Telegram Bot API to target specific topics within a supergroup.

## Design Decisions

Based on the spec in `.claude/specs/telegram-topic-support.md`:

1. **Compound Identifier** - Combined `chat_id:thread_id` format (e.g., `-1001234567890:123`) for internal identifier tracking
2. **Reject thread_id=1** - Prevents duplicate identifiers since General topic is accessed with thread_id=null
3. **Exact Match Detach** - Must specify exact thread_id to detach a destination
4. **Single Source of Truth** - `TelegramDestination.identifier` property delegates to helper functions

## Changes Made

### 1. Config Module (claude_session_player/watcher/config.py)

- Added `thread_id: int | None = None` field to `TelegramDestination`
- Added `identifier` property that uses `make_telegram_identifier()` helper
- Updated `to_dict()` to include thread_id when set
- Updated `from_dict()` to parse thread_id from config
- Updated `add_destination()` and `remove_destination()` to match by full identifier

### 2. Destinations Module (claude_session_player/watcher/destinations.py)

Added helper functions for compound identifier handling:

- `make_telegram_identifier(chat_id, thread_id)` - Creates `chat_id:thread_id` format
- `parse_telegram_identifier(identifier)` - Parses using `rsplit(":", 1)` to handle negative chat_ids

Updated `attach()`, `detach()`, and `restore_from_config()` to use parsed identifiers.

### 3. Telegram Publisher (claude_session_player/watcher/telegram_publisher.py)

- Added `message_thread_id: int | None = None` parameter to `send_message()`
- Passes `message_thread_id` to aiogram `Bot.send_message()` calls

### 4. REST API (claude_session_player/watcher/api.py)

- Updated `handle_attach()` to accept `thread_id` in destination payload
- Added validation to reject `thread_id=1` with error message
- Updated `handle_detach()` to parse and use thread_id for exact match
- Updated `handle_list_sessions()` to include thread_id in response

### 5. Bot Router (claude_session_player/watcher/bot_router.py)

- Updated type aliases to include thread_id parameter:
  - `TelegramCommandHandler` - Added Optional[int] for thread_id
  - `TelegramCallbackHandler` - Added Optional[int] for thread_id
- Extract `message_thread_id` from Telegram message and callback_query updates
- Pass thread_id to all handler calls

### 6. Telegram Commands (claude_session_player/watcher/telegram_commands.py)

- Updated `handle_search()` to accept thread_id and use compound identifier for state key
- Updated `handle_callback()` and all `_handle_*` methods to accept and pass thread_id
- Store thread_id in search state for use in Watch action callbacks
- Updated helper methods `_send_message_with_keyboard()` and `_send_reply()` to accept thread_id

### 7. Watcher Service (claude_session_player/watcher/service.py)

- Updated `_send_new_message()` to parse identifier and pass thread_id to publisher
- Updated `replay_to_destination()` to parse identifier and pass thread_id

### 8. Package Exports (claude_session_player/watcher/__init__.py)

- Added exports for `make_telegram_identifier` and `parse_telegram_identifier`

## Tests Added

### New Test File (tests/watcher/test_telegram_topic.py)

33 tests covering:

**Identifier Helper Tests (11 tests):**
- `TestMakeTelegramIdentifier` - 5 tests for make_telegram_identifier()
- `TestParseTelegramIdentifier` - 6 tests for parse_telegram_identifier()

**TelegramDestination Tests (8 tests):**
- `TestTelegramDestinationIdentifier` - 3 tests for identifier property
- `TestTelegramDestinationSerialization` - 5 tests for to_dict/from_dict roundtrip

**Destination Manager Tests (7 tests):**
- `TestAttachWithThreadId` - 3 tests for attach with thread_id
- `TestDetachWithThreadId` - 2 tests for detach exact match behavior
- `TestRestoreFromConfigWithThreadId` - 1 test for config restoration

**Module Import Tests (2 tests):**
- Test importing helpers from destinations module
- Test importing helpers from watcher package

**Integration Tests (3 tests):**
- `TestSendMessageToTopic` - Message sending includes thread_id
- Tests for replay_to_destination with thread_id

**API Tests (3 tests):**
- `TestAPIThreadIdValidation` - Tests for thread_id=1 rejection and valid thread_id acceptance
- Test for list_sessions including thread_id in response

### Updated Test Files

- `tests/watcher/test_api.py` - Updated error message assertion for missing identifier
- `tests/watcher/test_bot_router.py` - Updated handler signatures to include thread_id
- `tests/watcher/test_telegram_commands.py` - Updated callback test assertions for thread_id
- `tests/watcher/test_telegram_publisher.py` - Updated send_message assertions for message_thread_id
- `tests/watcher/test_messaging_integration.py` - Updated MockTelegramPublisher signature
- `tests/watcher/test_messaging_e2e.py` - Updated MockTelegramBot signature

## API Changes

### POST /attach

Request body now accepts `thread_id`:
```json
{
  "session_id": "my-session",
  "path": "/path/to/session.jsonl",
  "destination": {
    "type": "telegram",
    "chat_id": "-1001234567890",
    "thread_id": 123  // Optional
  }
}
```

Validation:
- `thread_id=1` is rejected with 400 error (use null for General topic)

### POST /detach

Request body accepts `thread_id` for exact match:
```json
{
  "session_id": "my-session",
  "destination": {
    "type": "telegram",
    "chat_id": "-1001234567890",
    "thread_id": 123  // Must match exactly
  }
}
```

### GET /sessions

Response includes thread_id:
```json
{
  "sessions": [{
    "session_id": "my-session",
    "destinations": {
      "telegram": [{
        "chat_id": "-1001234567890",
        "thread_id": 123
      }]
    }
  }]
}
```

## Test Results

All 2048 tests pass:
```
tests/watcher/test_telegram_topic.py: 33 passed
Full test suite: 2048 passed in ~4 minutes
```

## Files Changed

- `claude_session_player/watcher/__init__.py`
- `claude_session_player/watcher/api.py`
- `claude_session_player/watcher/bot_router.py`
- `claude_session_player/watcher/config.py`
- `claude_session_player/watcher/destinations.py`
- `claude_session_player/watcher/service.py`
- `claude_session_player/watcher/telegram_commands.py`
- `claude_session_player/watcher/telegram_publisher.py`
- `tests/watcher/test_api.py`
- `tests/watcher/test_bot_router.py`
- `tests/watcher/test_messaging_e2e.py`
- `tests/watcher/test_messaging_integration.py`
- `tests/watcher/test_telegram_commands.py`
- `tests/watcher/test_telegram_publisher.py`
- `tests/watcher/test_telegram_topic.py` (new)
