# Issue #73: Add MessageStateTracker for turn-based message grouping

## Summary

Implemented `MessageStateTracker` class for tracking message state across Telegram and Slack, handling turn-based grouping of events into messages. This component is essential for the messaging integration, determining when to send new messages vs update existing ones based on the turn grouping rules.

## Changes Made

### New Files

1. **`claude_session_player/watcher/message_state.py`**
   - `TurnState`: Dataclass tracking state of a single turn being built
   - `SessionMessageState`: Dataclass tracking message state for a single session
   - `SendNewMessage`: Action to send a new message to all destinations
   - `UpdateExistingMessage`: Action to update an existing message
   - `NoAction`: Action indicating no messaging action needed
   - `MessageAction`: Union type of all action types
   - `MessageStateTracker` class implementing:
     - `get_session_state()`: Get or create session state
     - `handle_event()`: Process event and determine messaging action
     - `record_message_id()`: Record message ID after sending
     - `get_message_id()`: Get message ID for a turn at a destination
     - `clear_session()`: Clear all state for a session
     - `render_replay()`: Render events as batched catch-up message

2. **`tests/watcher/test_message_state.py`**
   - 47 tests covering all functionality

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added imports for all new classes from message_state module
   - Updated `__all__` list with 7 new exports

## Design Decisions

### Turn Grouping Logic

Implemented the turn grouping rules from the spec:
- USER blocks create new messages and finalize previous turns
- ASSISTANT blocks start or continue turns (multiple ASSISTANT blocks concatenate)
- TOOL_CALL blocks are added to the current turn
- DURATION blocks are added as footers to the current turn
- SYSTEM blocks create standalone messages
- ClearAll events send "Context compacted" messages and clear state

### Message ID Tracking

Message IDs are tracked per-turn per-destination:
- Telegram: `dict[str, int]` mapping chat_id to message_id
- Slack: `dict[str, str]` mapping channel to timestamp

When a turn has message IDs recorded, subsequent events for that turn produce `UpdateExistingMessage` actions; otherwise they produce `SendNewMessage` actions.

### Tool Result Updates

Tool results are tracked by `tool_use_id` using an index mapping (`tool_use_id_to_index`). When an `UpdateBlock` event arrives, we look up the tool by its `tool_use_id` and update its result in place.

### Formatting Utilities

Imported formatting utilities from TelegramPublisher and SlackPublisher modules:
- `format_user_message()` / `format_user_message_blocks()`
- `format_turn_message()` / `format_turn_message_blocks()`
- `format_system_message()` / `format_system_message_blocks()`
- `format_context_compacted()` / `format_context_compacted_blocks()`
- `get_tool_icon()` / `slack_get_tool_icon()`

### Python 3.9 Compatibility

Used `Union[A, B, C]` syntax for the `MessageAction` type alias instead of the `A | B | C` syntax, since the test environment runs Python 3.9 which doesn't support the `|` syntax for type aliases at runtime.

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestTurnState | 2 | dataclass creation |
| TestSessionMessageState | 2 | dataclass creation |
| TestMessageActionTypes | 3 | action type creation |
| TestMessageStateTrackerBasic | 4 | session state management |
| TestHandleUserBlock | 3 | user block handling |
| TestHandleAssistantBlock | 3 | assistant block handling |
| TestHandleToolCallBlock | 5 | tool call block handling |
| TestHandleDurationBlock | 2 | duration block handling |
| TestHandleSystemBlock | 2 | system block handling |
| TestHandleUpdateBlock | 4 | update block handling |
| TestHandleClearAll | 3 | clear all handling |
| TestMessageIdTracking | 5 | message ID tracking |
| TestReplayRendering | 3 | replay rendering |
| TestOtherBlockTypes | 1 | thinking blocks |
| TestTurnGroupingIntegration | 2 | integration tests |
| TestModuleImports | 3 | package imports |

## Test Results

- **Before:** 1024 tests
- **After:** 1071 tests (47 new)
- All new tests pass

## Acceptance Criteria Status

- [x] `MessageStateTracker` class in `claude_session_player/watcher/message_state.py`
- [x] `TurnState` and `SessionMessageState` dataclasses
- [x] `MessageAction` union type with `SendNewMessage`, `UpdateExistingMessage`, `NoAction`
- [x] `handle_event()` correctly maps events to actions:
  - [x] USER → SendNewMessage + finalize previous turn
  - [x] ASSISTANT → SendNewMessage or UpdateExistingMessage (depending on state)
  - [x] TOOL_CALL → UpdateExistingMessage (add to turn)
  - [x] DURATION → UpdateExistingMessage (add footer)
  - [x] SYSTEM → SendNewMessage
  - [x] ClearAll → SendNewMessage (context compacted) + clear state
- [x] `record_message_id()` and `get_message_id()` for tracking sent messages
- [x] `render_replay()` produces batched catch-up content
- [x] Unit tests cover:
  - [x] Turn grouping: assistant + tools + duration in one turn
  - [x] Turn finalization on USER
  - [x] Multiple consecutive ASSISTANT blocks in one turn
  - [x] UpdateBlock handling for tool results
  - [x] ClearAll handling
  - [x] Message ID tracking
  - [x] Replay rendering
- [x] Formatting utilities imported from TelegramPublisher/SlackPublisher

## Spec Reference

Implements issue #73 from `.claude/specs/messaging-integration.md`:
- MessageStateTracker component for turn-based message grouping
- Ephemeral state management (not persisted)
- Integration with Telegram and Slack formatting utilities
