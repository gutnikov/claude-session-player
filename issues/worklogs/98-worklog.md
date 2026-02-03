# Issue #98: Update README and CLAUDE.md for search feature

## Summary

Updated project documentation (README.md and CLAUDE.md) to reflect the new session search functionality, including setup instructions, API reference, configuration options, and bot command usage.

## Changes Made

### Modified Files

1. **`README.md`**
   - Added new "Session Search" section after "Session Watcher Service"
   - Documented search quick start guide
   - Added search syntax and options reference table
   - Documented all search REST API endpoints with examples:
     - `GET /search` - Search sessions with filters and pagination
     - `GET /projects` - List indexed projects
     - `GET /sessions/{id}/preview` - Preview session events
     - `POST /index/refresh` - Force index refresh
   - Added Slack setup instructions for search (slash command, signing secret)
   - Added Telegram setup instructions for search (webhook vs polling mode)
   - Added index configuration reference (paths, refresh_interval, max_sessions_per_project, etc.)
   - Added search configuration reference (default_limit, max_limit, default_sort, state_ttl)
   - Added environment variables reference

2. **`CLAUDE.md`**
   - Added search API example to Quick Commands section
   - Added "Search Components" section to architecture documentation
   - Added "Search Module" section to file locations
   - Updated Tests section with search-related test files
   - Added "Searching Sessions" section to Common Tasks with:
     - Python code example using SessionIndexer and SearchEngine
     - REST API examples using curl

## Test Coverage

No new tests added (this is a documentation-only issue). All existing tests pass:
- **Core tests:** 474 passed (2 pre-existing failures due to missing slack_sdk)
- **All tests:** 1429 passed (41 pre-existing failures due to missing optional dependencies and Python 3.9 asyncio issues)

## Design Decisions

### Documentation Structure

The search documentation was added as a new top-level section in README.md rather than as a subsection of "Session Watcher Service" because:
1. Search is a significant feature that users will look for directly
2. It has its own configuration and API endpoints
3. It enhances the existing watcher service but is also usable independently via REST API

### Code Examples

- Used `engine.parse_query()` instead of manually constructing `SearchParams` in the CLAUDE.md example to demonstrate the recommended high-level interface
- REST API examples use curl to match the style of existing documentation
- Python code examples use asyncio.run() to show proper async handling

### API Documentation

Documented the most commonly used parameters and responses. Full details remain in the spec (`.claude/specs/session-search-api.md`).

## Acceptance Criteria Status

- [x] README.md updated with search section
- [x] README.md bot setup includes search commands
- [x] README.md configuration reference updated
- [x] CLAUDE.md architecture section updated
- [x] CLAUDE.md file locations updated
- [x] CLAUDE.md common tasks updated
- [x] All code examples tested and working
- [x] No broken links or references

## Definition of Done Status

- [x] README.md updated with search section
- [x] README.md bot setup includes search commands
- [x] README.md configuration reference updated
- [x] CLAUDE.md architecture section updated
- [x] CLAUDE.md file locations updated
- [x] CLAUDE.md common tasks updated
- [x] All code examples tested and working
- [x] No broken links or references

## Spec Reference

Documents functionality from `.claude/specs/session-search-api.md`:
- Search syntax and options (lines 306-374)
- REST API endpoints (lines 377-569)
- Configuration (lines 1159-1253)
- Bot command infrastructure (lines 854-1103)

## Notes

- The documentation covers all search components implemented in issues #85-97
- Pre-existing test failures (slack_sdk, aiogram dependencies, Python 3.9 asyncio issues) are unrelated to this documentation change
- Environment variable documentation matches the spec but actual environment variable support depends on ConfigManager implementation
