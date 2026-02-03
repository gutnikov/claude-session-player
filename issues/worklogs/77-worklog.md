# Issue #77: Update README and CLAUDE.md for messaging integration

## Summary

Updated all documentation to reflect the new Slack and Telegram messaging integration, including setup instructions, API changes, and architecture updates.

## Changes Made

### Modified Files

1. **`README.md`**
   - Added Messaging Integration section with:
     - Telegram setup instructions
     - Slack setup instructions
     - Configuration file format (config.yaml)
   - Replaced `/watch` and `/unwatch` endpoints with `/attach` and `/detach`
   - Updated API endpoint table with new endpoints
   - Updated API documentation with request/response examples
   - Added `bots` status to health check documentation
   - Added `destinations` to session list response documentation
   - Added `replay_count` parameter documentation
   - Added Troubleshooting section for common messaging issues
   - Added Breaking Changes section documenting v0.5.0 API changes

2. **`CLAUDE.md`**
   - Updated Watcher Module file locations to include:
     - `destinations.py` - Destination lifecycle management
     - `telegram_publisher.py` - Telegram Bot API integration
     - `slack_publisher.py` - Slack Web API integration
     - `message_state.py` - Turn-based message grouping
     - `debouncer.py` - Rate limiting for message updates
     - `deps.py` - Optional dependency checking
   - Updated Common Tasks section:
     - Replaced `/watch` example with `/attach` and `/detach` examples
   - Updated Watcher Architecture section:
     - New architecture diagram showing messaging components
     - Event flow diagram showing path to Telegram/Slack
   - Updated Key Components list with:
     - DestinationManager
     - TelegramPublisher
     - SlackPublisher
     - MessageStateTracker
     - MessageDebouncer
   - Added Configuration section with config.yaml example
   - Added messaging integration test file to Tests section

## Design Decisions

### Documentation Structure

Kept the README.md as the primary user-facing documentation with:
- Quick setup instructions for Telegram and Slack
- Complete API reference with curl examples
- Troubleshooting tips for common issues

CLAUDE.md focuses on developer context with:
- Architecture diagrams
- File locations
- Event flow details
- Common development tasks

### Breaking Changes Documentation

Added a dedicated Breaking Changes section at the end of README.md to clearly communicate:
- API endpoint changes (`/watch` → `/attach`, `/unwatch` → `/detach`)
- Config file format changes
- Version number (v0.5.0) for tracking

### Installation Dependencies

Documented two levels of optional dependencies:
- `[watcher]` - Core watcher dependencies (aiohttp, watchfiles, pyyaml)
- `[messaging]` - Messaging dependencies (aiogram, slack-sdk)

## Test Results

- Core tests (parser, processor, consumer, etc.): 231 passed
- Watcher tests with optional deps not installed: some tests skip as expected
- This is a documentation-only change, no code changes were made

## Acceptance Criteria Status

- [x] README.md updated:
  - [x] Messaging Integration section added
  - [x] Telegram setup instructions
  - [x] Slack setup instructions
  - [x] attach/detach API examples
  - [x] replay_count documented
  - [x] Optional dependencies noted
  - [x] API endpoint table updated
- [x] CLAUDE.md updated:
  - [x] Architecture diagram includes messaging components
  - [x] File locations updated with new modules
  - [x] Event flow updated
  - [x] Config format documented
  - [x] Common tasks updated
- [x] Breaking changes documented
- [x] All curl examples accurate to current API
- [x] No stale references to watch/unwatch

## Spec Reference

Implements issue #77 from `.claude/specs/messaging-integration.md`:
- Documentation updates for messaging integration
- API migration guide from watch/unwatch to attach/detach
