# Issue #110: Add aiosqlite dependency for search index

## Summary

Added `aiosqlite>=0.19.0` as a dependency for the SQLite-based search index to the `watcher` optional dependencies.

## Changes Made

### Modified Files

1. **`pyproject.toml`**
   - Added `aiosqlite>=0.19.0` to the `watcher` optional dependencies
   - Full dependency list now: `["pyyaml>=6.0", "watchfiles>=0.21", "aiohttp>=3.0", "aiosqlite>=0.19.0"]`

## Version Selection Rationale

- `aiosqlite>=0.19.0`: Stable async SQLite wrapper, supports Python 3.8+
- No upper bound: Allow minor/patch updates
- 0.19.0 minimum: Includes `backup()` method needed for database backups per the spec

## Verification

1. **Installation verified:**
   ```
   $ uv pip install -e ".[watcher]"
   + aiosqlite==0.22.1
   ```

2. **Import verified:**
   ```python
   $ python -c "import aiosqlite; print(f'aiosqlite version: {aiosqlite.__version__}')"
   aiosqlite version: 0.22.1
   ```

3. **All tests pass:** 1582 passed

## README Update

Not needed. The README already instructs users to install with `pip install "claude-session-player[watcher]"` which automatically includes all watcher dependencies including the new `aiosqlite` package.

## CI Update

Not applicable. No CI configuration exists in this project yet.

## Definition of Done Status

- [x] Dependency added to pyproject.toml
- [x] Installation verified locally (`pip install -e ".[watcher]"` succeeds)
- [x] Import works (`import aiosqlite` succeeds)
- [x] All tests pass (1582 passed)
- [x] README updated if needed (not needed - users already instructed to use `[watcher]` extras)
- [x] CI passes (N/A - no CI configured)

## Spec Reference

This issue implements the "Dependencies" section from `.claude/specs/sqlite-search-index.md` (lines 1553-1575):
- Required: `aiosqlite>=0.19.0` - Async SQLite wrapper

## Blocks

This unblocks:
- SearchDatabase core implementation (issue #111)
