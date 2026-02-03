# Issue #76: Integrate messaging components into WatcherService

## Summary

Integrated all messaging components (TelegramPublisher, SlackPublisher, MessageStateTracker, MessageDebouncer, DestinationManager) into the WatcherService for end-to-end Telegram and Slack notifications.

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/service.py`**
   - Added imports for all messaging components:
     - `MessageDebouncer`, `AttachedDestination`, `DestinationManager`
     - `MessageStateTracker`, `NoAction`, `SendNewMessage`, `UpdateExistingMessage`
     - `TelegramError`, `TelegramPublisher`, `SlackError`, `SlackPublisher`
   - Added new dataclass fields:
     - `telegram_publisher: TelegramPublisher | None`
     - `slack_publisher: SlackPublisher | None`
     - `message_state: MessageStateTracker | None`
     - `message_debouncer: MessageDebouncer | None`
   - Updated `__post_init__()`:
     - Creates TelegramPublisher if telegram token configured in bot_config
     - Creates SlackPublisher if slack token configured in bot_config
     - Always creates MessageStateTracker and MessageDebouncer
     - Injects replay_callback into WatcherAPI
   - Updated `start()`:
     - Restores messaging destinations from config on startup
   - Updated `stop()`:
     - Flushes pending debounced updates
     - Closes Telegram and Slack publishers
   - Updated `_on_file_change()`:
     - Publishes events to messaging destinations after SSE broadcast
   - Updated `_on_destination_session_stop()`:
     - Clears message state when session stops
   - Added new messaging methods:
     - `_publish_to_messaging()`: Dispatches events to MessageStateTracker
     - `_publish_action_to_destination()`: Routes actions to send/update
     - `_send_new_message()`: Sends new messages to Telegram/Slack
     - `_update_message()`: Schedules debounced message updates
     - `replay_to_destination()`: Sends batched catch-up messages
     - `validate_destination()`: Validates bot credentials on demand

2. **`claude_session_player/watcher/api.py`**
   - Added `ReplayCallback` type alias
   - Added `replay_callback: ReplayCallback | None` field to WatcherAPI
   - Updated `_replay_to_destination()` to use injected callback

### New Files

1. **`tests/watcher/test_messaging_integration.py`**
   - 21 integration tests covering:
     - Service initialization with messaging components
     - Event flow to Telegram/Slack destinations
     - Turn grouping (assistant + tools in one message)
     - Message update debouncing
     - Replay functionality
     - Graceful shutdown (flush debouncer, close publishers)
     - Error handling (failures logged, not raised)
     - ClearAll (context compaction) handling
     - Multiple destinations (same type and mixed)
     - Service startup with restored destinations

## Design Decisions

### Callback Injection for Replay

The WatcherAPI doesn't have direct access to WatcherService (to avoid circular dependencies). Instead of adding the service as a dependency, a `replay_callback` is injected that delegates to `service.replay_to_destination()`. This maintains clean separation of concerns.

### Lazy Publisher Creation

Publishers are only created if their token is configured in `bot_config`. This allows the service to run without any messaging configured (graceful degradation).

### Message State Clearing on Session Stop

When a session stops (no more destinations), message state is cleared. This ensures we don't accumulate stale turn state for sessions that are no longer active.

### Error Handling Strategy

Messaging failures are logged as warnings but don't raise exceptions. This prevents a single failed destination from blocking delivery to other destinations or disrupting SSE streaming.

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestServiceMessagingInitialization | 6 | component creation |
| TestEventFlowToMessaging | 5 | user/assistant blocks, turn grouping, debouncing |
| TestReplayToDestination | 2 | replay with/without events |
| TestMessagingShutdown | 2 | flush debouncer, close publishers |
| TestMessagingErrorHandling | 2 | failures logged, validation |
| TestClearAllEvent | 1 | context compaction |
| TestMultipleDestinations | 2 | all destinations, multiple chats |
| TestServiceStartWithDestinations | 1 | restore from config |

## Test Results

- **Before:** 1097 tests
- **After:** 1119 tests (21 new + 1 from prior pass)
- All tests pass

## Acceptance Criteria Status

- [x] WatcherService imports and initializes all messaging components
- [x] Publishers created based on bot config (lazy, only if token present)
- [x] `_on_file_change` publishes to messaging destinations
- [x] New messages sent immediately
- [x] Message updates debounced
- [x] Message IDs tracked in MessageStateTracker
- [x] `replay_to_destination()` sends batched catch-up message
- [x] `validate_destination()` validates credentials on demand
- [x] Graceful shutdown flushes pending updates and closes publishers
- [x] Integration tests:
  - [x] End-to-end: file change → Telegram message (mocked)
  - [x] End-to-end: file change → Slack message (mocked)
  - [x] Turn grouping in messages
  - [x] Message updates debounced
  - [x] Replay on attach
  - [x] Credentials validated on first attach
- [x] Service starts without messaging deps (graceful degradation)

## Spec Reference

Implements issue #76 from `.claude/specs/messaging-integration.md`:
- Main integration point connecting all messaging components
- End-to-end event flow from FileWatcher to Telegram/Slack
- Proper shutdown sequence with flush and close
