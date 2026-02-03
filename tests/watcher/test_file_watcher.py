"""Tests for FileWatcher and IncrementalReader."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.watcher.file_watcher import (
    FileWatcher,
    IncrementalReader,
    WatchedFile,
)


# ---------------------------------------------------------------------------
# IncrementalReader tests
# ---------------------------------------------------------------------------


class TestIncrementalReaderCreation:
    """Tests for IncrementalReader creation."""

    def test_create_with_path(self, tmp_path: Path) -> None:
        """Can create IncrementalReader with path."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")
        reader = IncrementalReader(path=file_path)
        assert reader.path == file_path
        assert reader.position == 0

    def test_create_with_position(self, tmp_path: Path) -> None:
        """Can create IncrementalReader with custom position."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")
        reader = IncrementalReader(path=file_path, position=100)
        assert reader.position == 100


class TestIncrementalReaderReadNewLines:
    """Tests for IncrementalReader.read_new_lines()."""

    def test_read_new_lines_returns_parsed_json(self, tmp_path: Path) -> None:
        """read_new_lines() returns parsed JSON objects."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"type": "user", "text": "hello"}\n')
        reader = IncrementalReader(path=file_path, position=0)

        lines, new_pos = reader.read_new_lines()

        assert len(lines) == 1
        assert lines[0] == {"type": "user", "text": "hello"}
        assert new_pos > 0

    def test_read_new_lines_multiple_lines(self, tmp_path: Path) -> None:
        """read_new_lines() handles multiple JSON lines."""
        file_path = tmp_path / "test.jsonl"
        content = '{"line": 1}\n{"line": 2}\n{"line": 3}\n'
        file_path.write_text(content)
        reader = IncrementalReader(path=file_path, position=0)

        lines, new_pos = reader.read_new_lines()

        assert len(lines) == 3
        assert lines[0] == {"line": 1}
        assert lines[1] == {"line": 2}
        assert lines[2] == {"line": 3}

    def test_read_new_lines_incremental(self, tmp_path: Path) -> None:
        """read_new_lines() only reads new content since last position."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n')
        reader = IncrementalReader(path=file_path, position=0)

        # First read
        lines1, pos1 = reader.read_new_lines()
        assert len(lines1) == 1
        assert lines1[0] == {"line": 1}

        # Append more content
        with open(file_path, "a") as f:
            f.write('{"line": 2}\n')

        # Second read - only gets new line
        lines2, pos2 = reader.read_new_lines()
        assert len(lines2) == 1
        assert lines2[0] == {"line": 2}
        assert pos2 > pos1

    def test_read_new_lines_partial_line_not_consumed(self, tmp_path: Path) -> None:
        """read_new_lines() does not consume partial lines at EOF."""
        file_path = tmp_path / "test.jsonl"
        # Write complete line followed by incomplete line (no newline)
        file_path.write_text('{"complete": true}\n{"incomplete": true')
        reader = IncrementalReader(path=file_path, position=0)

        lines, new_pos = reader.read_new_lines()

        # Should only get the complete line
        assert len(lines) == 1
        assert lines[0] == {"complete": True}

        # Now complete the partial line
        with open(file_path, "a") as f:
            f.write("}\n")

        lines2, _ = reader.read_new_lines()
        assert len(lines2) == 1
        assert lines2[0] == {"incomplete": True}

    def test_read_new_lines_skips_empty_lines(self, tmp_path: Path) -> None:
        """read_new_lines() skips empty lines."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n\n{"line": 2}\n  \n{"line": 3}\n')
        reader = IncrementalReader(path=file_path, position=0)

        lines, _ = reader.read_new_lines()

        assert len(lines) == 3

    def test_read_new_lines_skips_malformed_json(self, tmp_path: Path) -> None:
        """read_new_lines() skips malformed JSON lines with warning."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"valid": 1}\nnot valid json\n{"valid": 2}\n')
        reader = IncrementalReader(path=file_path, position=0)

        lines, _ = reader.read_new_lines()

        # Should skip the malformed line
        assert len(lines) == 2
        assert lines[0] == {"valid": 1}
        assert lines[1] == {"valid": 2}

    def test_read_new_lines_handles_file_truncation(self, tmp_path: Path) -> None:
        """read_new_lines() resets position when file is truncated."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n' * 10)  # Create large file
        reader = IncrementalReader(path=file_path, position=0)

        # Read to end
        reader.read_new_lines()
        old_pos = reader.position

        # Truncate file to smaller size
        file_path.write_text('{"new": 1}\n')

        # Position should reset since it's past EOF
        lines, new_pos = reader.read_new_lines()

        assert reader.position < old_pos
        assert len(lines) == 1
        assert lines[0] == {"new": 1}

    def test_read_new_lines_file_deleted(self, tmp_path: Path) -> None:
        """read_new_lines() returns empty list if file deleted."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n')
        reader = IncrementalReader(path=file_path, position=0)

        # Delete the file
        file_path.unlink()

        lines, pos = reader.read_new_lines()

        assert lines == []
        assert pos == 0  # Position unchanged

    def test_read_new_lines_no_new_content(self, tmp_path: Path) -> None:
        """read_new_lines() returns empty list when no new content."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n')
        reader = IncrementalReader(path=file_path, position=0)

        # First read
        reader.read_new_lines()

        # Second read without new content
        lines, _ = reader.read_new_lines()

        assert lines == []

    def test_read_new_lines_updates_position(self, tmp_path: Path) -> None:
        """read_new_lines() updates reader's internal position."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n{"line": 2}\n')
        reader = IncrementalReader(path=file_path, position=0)

        _, new_pos = reader.read_new_lines()

        assert reader.position == new_pos
        assert new_pos > 0


class TestIncrementalReaderSeekToLastNLines:
    """Tests for IncrementalReader.seek_to_last_n_lines()."""

    def test_seek_to_last_3_lines(self, tmp_path: Path) -> None:
        """seek_to_last_n_lines(3) positions at 3rd-to-last line."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n{"line": 2}\n{"line": 3}\n{"line": 4}\n{"line": 5}\n')
        reader = IncrementalReader(path=file_path)

        position = reader.seek_to_last_n_lines(3)

        # Now read from that position
        lines, _ = reader.read_new_lines()
        assert len(lines) == 3
        assert lines[0] == {"line": 3}
        assert lines[1] == {"line": 4}
        assert lines[2] == {"line": 5}

    def test_seek_to_last_n_lines_fewer_than_n(self, tmp_path: Path) -> None:
        """seek_to_last_n_lines() returns 0 if file has fewer than n lines."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n{"line": 2}\n')
        reader = IncrementalReader(path=file_path)

        position = reader.seek_to_last_n_lines(5)

        assert position == 0
        # Should get all lines
        lines, _ = reader.read_new_lines()
        assert len(lines) == 2

    def test_seek_to_last_n_lines_empty_file(self, tmp_path: Path) -> None:
        """seek_to_last_n_lines() returns 0 for empty file."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")
        reader = IncrementalReader(path=file_path)

        position = reader.seek_to_last_n_lines(3)

        assert position == 0

    def test_seek_to_last_n_lines_file_not_found(self, tmp_path: Path) -> None:
        """seek_to_last_n_lines() returns 0 if file doesn't exist."""
        file_path = tmp_path / "nonexistent.jsonl"
        reader = IncrementalReader(path=file_path)

        position = reader.seek_to_last_n_lines(3)

        assert position == 0

    def test_seek_to_last_n_lines_with_empty_lines(self, tmp_path: Path) -> None:
        """seek_to_last_n_lines() counts only non-empty lines."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n\n{"line": 2}\n\n{"line": 3}\n')
        reader = IncrementalReader(path=file_path)

        position = reader.seek_to_last_n_lines(2)

        # Should position at line 2 (2nd-to-last non-empty)
        lines, _ = reader.read_new_lines()
        assert len(lines) == 2
        assert lines[0] == {"line": 2}
        assert lines[1] == {"line": 3}

    def test_seek_to_last_n_lines_updates_position(self, tmp_path: Path) -> None:
        """seek_to_last_n_lines() updates reader's internal position."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n{"line": 2}\n{"line": 3}\n')
        reader = IncrementalReader(path=file_path)

        position = reader.seek_to_last_n_lines(2)

        assert reader.position == position


# ---------------------------------------------------------------------------
# WatchedFile tests
# ---------------------------------------------------------------------------


class TestWatchedFile:
    """Tests for WatchedFile dataclass."""

    def test_create_watched_file(self, tmp_path: Path) -> None:
        """Can create WatchedFile with all fields."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")
        reader = IncrementalReader(path=file_path)

        watched = WatchedFile(
            session_id="session-001",
            path=file_path,
            reader=reader,
        )

        assert watched.session_id == "session-001"
        assert watched.path == file_path
        assert watched.reader == reader


# ---------------------------------------------------------------------------
# FileWatcher tests
# ---------------------------------------------------------------------------


class TestFileWatcherCreation:
    """Tests for FileWatcher creation."""

    def test_create_with_callback(self) -> None:
        """Can create FileWatcher with callback."""
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)

        assert watcher.on_lines_callback == callback
        assert watcher.on_file_deleted_callback is None
        assert not watcher.is_running
        assert watcher.watched_sessions == []

    def test_create_with_delete_callback(self) -> None:
        """Can create FileWatcher with delete callback."""
        lines_callback = AsyncMock()
        delete_callback = AsyncMock()

        watcher = FileWatcher(
            on_lines_callback=lines_callback,
            on_file_deleted_callback=delete_callback,
        )

        assert watcher.on_file_deleted_callback == delete_callback


class TestFileWatcherAddRemove:
    """Tests for FileWatcher.add() and .remove()."""

    def test_add_file_to_watch(self, tmp_path: Path) -> None:
        """add() registers a file for watching."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)

        watcher.add("session-001", file_path, start_position=0)

        assert "session-001" in watcher.watched_sessions
        assert watcher.get_position("session-001") == 0

    def test_add_file_with_position(self, tmp_path: Path) -> None:
        """add() accepts start_position parameter."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n')
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)

        watcher.add("session-001", file_path, start_position=100)

        assert watcher.get_position("session-001") == 100

    def test_add_multiple_files(self, tmp_path: Path) -> None:
        """add() can register multiple files."""
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)

        for i in range(5):
            file_path = tmp_path / f"test{i}.jsonl"
            file_path.write_text("")
            watcher.add(f"session-{i}", file_path, start_position=0)

        assert len(watcher.watched_sessions) == 5

    def test_remove_file_from_watch(self, tmp_path: Path) -> None:
        """remove() unregisters a file from watching."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)
        watcher.add("session-001", file_path, start_position=0)

        watcher.remove("session-001")

        assert "session-001" not in watcher.watched_sessions

    def test_remove_nonexistent_session(self) -> None:
        """remove() does nothing for non-existent session."""
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)

        # Should not raise
        watcher.remove("nonexistent")

    def test_get_position_nonexistent_session(self) -> None:
        """get_position() returns None for non-existent session."""
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)

        assert watcher.get_position("nonexistent") is None


class TestFileWatcherStartStop:
    """Tests for FileWatcher.start() and .stop()."""

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self, tmp_path: Path) -> None:
        """start() sets is_running to True."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)
        watcher.add("session-001", file_path, start_position=0)

        await watcher.start()
        try:
            assert watcher.is_running
        finally:
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self, tmp_path: Path) -> None:
        """stop() sets is_running to False."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)
        watcher.add("session-001", file_path, start_position=0)

        await watcher.start()
        await watcher.stop()

        assert not watcher.is_running

    @pytest.mark.asyncio
    async def test_start_idempotent(self, tmp_path: Path) -> None:
        """start() is idempotent - calling twice is safe."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)
        watcher.add("session-001", file_path, start_position=0)

        await watcher.start()
        await watcher.start()  # Second call should be safe
        try:
            assert watcher.is_running
        finally:
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        """stop() is idempotent - calling twice is safe."""
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)

        # Should not raise even if not started
        await watcher.stop()
        await watcher.stop()


class TestFileWatcherProcessInitial:
    """Tests for FileWatcher.process_initial()."""

    @pytest.mark.asyncio
    async def test_process_initial_calls_callback(self, tmp_path: Path) -> None:
        """process_initial() calls callback with last N lines."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n{"line": 2}\n{"line": 3}\n{"line": 4}\n{"line": 5}\n')
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)
        watcher.add("session-001", file_path, start_position=0)

        await watcher.process_initial("session-001", last_n_lines=3)

        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == "session-001"
        assert len(args[1]) == 3
        assert args[1][0] == {"line": 3}
        assert args[1][1] == {"line": 4}
        assert args[1][2] == {"line": 5}

    @pytest.mark.asyncio
    async def test_process_initial_nonexistent_session(self) -> None:
        """process_initial() does nothing for non-existent session."""
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)

        await watcher.process_initial("nonexistent")

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_initial_empty_file(self, tmp_path: Path) -> None:
        """process_initial() does not call callback for empty file."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)
        watcher.add("session-001", file_path, start_position=0)

        await watcher.process_initial("session-001")

        callback.assert_not_called()


class TestFileWatcherFileChanges:
    """Tests for file change detection and processing."""

    @pytest.mark.asyncio
    async def test_detects_new_lines_appended(self, tmp_path: Path) -> None:
        """FileWatcher detects and processes new lines appended to file."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"initial": true}\n')
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)
        watcher.add("session-001", file_path, start_position=0)

        # Read initial content
        await watcher.process_initial("session-001", last_n_lines=10)
        callback.reset_mock()

        # Simulate file change detection by calling internal handler
        # Append new content
        with open(file_path, "a") as f:
            f.write('{"new": true}\n')

        # Manually trigger change handling (simulates watchfiles event)
        from watchfiles import Change

        await watcher._handle_changes({(Change.modified, str(file_path.resolve()))})

        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == "session-001"
        assert len(args[1]) == 1
        assert args[1][0] == {"new": True}

    @pytest.mark.asyncio
    async def test_file_deletion_triggers_callback(self, tmp_path: Path) -> None:
        """File deletion triggers on_file_deleted_callback."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n')
        lines_callback = AsyncMock()
        delete_callback = AsyncMock()
        watcher = FileWatcher(
            on_lines_callback=lines_callback,
            on_file_deleted_callback=delete_callback,
        )
        watcher.add("session-001", file_path, start_position=0)

        # Simulate file deletion event
        from watchfiles import Change

        await watcher._handle_changes({(Change.deleted, str(file_path.resolve()))})

        delete_callback.assert_called_once_with("session-001")
        assert "session-001" not in watcher.watched_sessions

    @pytest.mark.asyncio
    async def test_file_deletion_without_callback(self, tmp_path: Path) -> None:
        """File deletion removes session even without delete callback."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n')
        lines_callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=lines_callback)
        watcher.add("session-001", file_path, start_position=0)

        # Simulate file deletion event
        from watchfiles import Change

        await watcher._handle_changes({(Change.deleted, str(file_path.resolve()))})

        assert "session-001" not in watcher.watched_sessions

    @pytest.mark.asyncio
    async def test_ignores_untracked_file_changes(self, tmp_path: Path) -> None:
        """FileWatcher ignores changes to files not being watched."""
        file_path = tmp_path / "watched.jsonl"
        file_path.write_text("")
        untracked_path = tmp_path / "untracked.jsonl"
        untracked_path.write_text('{"line": 1}\n')

        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)
        watcher.add("session-001", file_path, start_position=0)

        # Simulate change to untracked file
        from watchfiles import Change

        await watcher._handle_changes({(Change.modified, str(untracked_path.resolve()))})

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_concurrent_file_watches(self, tmp_path: Path) -> None:
        """FileWatcher handles multiple files concurrently."""
        callback = AsyncMock()
        watcher = FileWatcher(on_lines_callback=callback)

        # Create and watch multiple files
        paths = []
        for i in range(3):
            file_path = tmp_path / f"test{i}.jsonl"
            file_path.write_text(f'{{"session": {i}}}\n')
            paths.append(file_path)
            watcher.add(f"session-{i}", file_path, start_position=0)

        # Process initial for all
        for i in range(3):
            await watcher.process_initial(f"session-{i}")

        assert callback.call_count == 3

        # Verify all sessions are tracked
        assert len(watcher.watched_sessions) == 3


class TestFileWatcherIntegration:
    """Integration tests for FileWatcher with real file writes."""

    @pytest.mark.asyncio
    async def test_integration_file_append(self, tmp_path: Path) -> None:
        """Integration test: append lines to file and detect them."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"initial": true}\n')

        received_lines: list[tuple[str, list[dict]]] = []

        async def capture_callback(session_id: str, lines: list[dict]) -> None:
            received_lines.append((session_id, lines))

        watcher = FileWatcher(on_lines_callback=capture_callback)
        watcher.add("test-session", file_path, start_position=0)

        # Read initial
        await watcher.process_initial("test-session", last_n_lines=10)

        assert len(received_lines) == 1
        assert received_lines[0][0] == "test-session"
        assert received_lines[0][1] == [{"initial": True}]

        # Append new lines
        with open(file_path, "a") as f:
            f.write('{"new1": true}\n')
            f.write('{"new2": true}\n')

        # Manually trigger (in real usage, watchfiles would do this)
        from watchfiles import Change

        await watcher._handle_changes({(Change.modified, str(file_path.resolve()))})

        assert len(received_lines) == 2
        assert received_lines[1][1] == [{"new1": True}, {"new2": True}]

    @pytest.mark.asyncio
    async def test_integration_full_lifecycle(self, tmp_path: Path) -> None:
        """Integration test: full watch lifecycle."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")

        lines_received: list[dict] = []
        deleted_sessions: list[str] = []

        async def on_lines(session_id: str, lines: list[dict]) -> None:
            lines_received.extend(lines)

        async def on_deleted(session_id: str) -> None:
            deleted_sessions.append(session_id)

        watcher = FileWatcher(
            on_lines_callback=on_lines,
            on_file_deleted_callback=on_deleted,
        )

        # Add and start
        watcher.add("session-001", file_path, start_position=0)
        await watcher.start()

        try:
            # Write content
            with open(file_path, "a") as f:
                f.write('{"type": "user"}\n')
                f.write('{"type": "assistant"}\n')

            # Manually trigger change (simulates watchfiles)
            from watchfiles import Change

            await watcher._handle_changes({(Change.modified, str(file_path.resolve()))})

            assert len(lines_received) == 2

            # Simulate deletion
            await watcher._handle_changes({(Change.deleted, str(file_path.resolve()))})

            assert "session-001" in deleted_sessions
            assert "session-001" not in watcher.watched_sessions

        finally:
            await watcher.stop()


class TestFileWatcherErrorHandling:
    """Tests for error handling in FileWatcher."""

    @pytest.mark.asyncio
    async def test_callback_error_does_not_crash_watcher(self, tmp_path: Path) -> None:
        """Errors in callback do not crash the watcher."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n')

        async def failing_callback(session_id: str, lines: list[dict]) -> None:
            raise ValueError("Callback error")

        watcher = FileWatcher(on_lines_callback=failing_callback)
        watcher.add("session-001", file_path, start_position=0)

        # Should not raise, error should be logged
        from watchfiles import Change

        await watcher._handle_changes({(Change.modified, str(file_path.resolve()))})

        # Watcher should still be functional
        assert "session-001" in watcher.watched_sessions

    @pytest.mark.asyncio
    async def test_delete_callback_error_does_not_crash(self, tmp_path: Path) -> None:
        """Errors in delete callback do not crash the watcher."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text('{"line": 1}\n')

        lines_callback = AsyncMock()

        async def failing_delete_callback(session_id: str) -> None:
            raise ValueError("Delete callback error")

        watcher = FileWatcher(
            on_lines_callback=lines_callback,
            on_file_deleted_callback=failing_delete_callback,
        )
        watcher.add("session-001", file_path, start_position=0)

        # Should not raise, error should be logged
        from watchfiles import Change

        await watcher._handle_changes({(Change.deleted, str(file_path.resolve()))})

        # Session should still be removed
        assert "session-001" not in watcher.watched_sessions
