"""File watcher with incremental JSONL reading."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from watchfiles import Change, awatch

logger = logging.getLogger(__name__)


@dataclass
class IncrementalReader:
    """Helper for incrementally reading new lines from a JSONL file.

    Tracks position in the file and reads only new content since last read.
    Handles partial lines at EOF and file truncation gracefully.
    """

    path: Path
    position: int = 0

    def read_new_lines(self) -> tuple[list[dict], int]:
        """Read new lines from the file starting at saved position.

        Returns:
            Tuple of (parsed lines, new position).
            Lines that fail JSON parsing are skipped with a warning.

        Notes:
            - Handles partial lines at EOF by not consuming incomplete JSON
            - Handles file truncation by resetting position to 0
        """
        try:
            file_size = self.path.stat().st_size
        except FileNotFoundError:
            # File was deleted
            return [], self.position

        # Handle file truncation (position > file size)
        if self.position > file_size:
            logger.warning(
                f"File truncated: {self.path} (position {self.position} > size {file_size}), "
                "resetting to 0"
            )
            self.position = 0

        if self.position >= file_size:
            # No new content
            return [], self.position

        with open(self.path, "rb") as f:
            f.seek(self.position)
            raw_data = f.read()

        # Decode to string, handling potential encoding issues
        try:
            text = raw_data.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(f"Unicode decode error in {self.path}, skipping chunk")
            # Move position to end to avoid getting stuck
            return [], file_size

        # Split into lines but keep track of whether last line is complete
        lines = text.split("\n")
        parsed_lines: list[dict] = []

        # If the text doesn't end with newline, the last line is incomplete
        # We should not process it yet
        if text and not text.endswith("\n"):
            incomplete_line = lines[-1]
            lines = lines[:-1]
            # Adjust position to not include the incomplete line
            bytes_consumed = len(text.encode("utf-8")) - len(incomplete_line.encode("utf-8"))
        else:
            bytes_consumed = len(raw_data)

        for line in lines:
            line = line.strip()
            if not line:
                # Skip empty lines
                continue

            try:
                parsed = json.loads(line)
                parsed_lines.append(parsed)
            except json.JSONDecodeError as e:
                logger.warning(f"Malformed JSON in {self.path}: {e}")
                # Skip malformed lines

        new_position = self.position + bytes_consumed
        self.position = new_position
        return parsed_lines, new_position

    def seek_to_last_n_lines(self, n: int) -> int:
        """Seek to the position of the nth-to-last line in the file.

        Used for initial watch to get some context without reading entire file.

        Args:
            n: Number of lines from the end to seek to.

        Returns:
            Position (byte offset) of the nth-to-last line.
            Returns 0 if file has fewer than n lines.
        """
        try:
            file_size = self.path.stat().st_size
        except FileNotFoundError:
            return 0

        if file_size == 0:
            return 0

        # Read the entire file to find line positions
        # For very large files, a chunked approach would be better,
        # but for typical JSONL session files this is fine
        with open(self.path, "rb") as f:
            content = f.read()

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(f"Unicode decode error in {self.path}")
            return file_size

        # Find all line endings
        lines = text.split("\n")

        # Filter out empty lines and count real lines
        non_empty_indices: list[int] = []
        current_pos = 0
        for i, line in enumerate(lines):
            if line.strip():
                non_empty_indices.append(current_pos)
            # Account for the newline character except for the last segment
            current_pos += len(line.encode("utf-8"))
            if i < len(lines) - 1:
                current_pos += 1  # newline byte

        if len(non_empty_indices) <= n:
            # File has n or fewer lines, start from beginning
            return 0

        # Get position of nth-to-last line
        target_index = len(non_empty_indices) - n
        position = non_empty_indices[target_index]
        self.position = position
        return position


@dataclass
class WatchedFile:
    """Internal representation of a file being watched."""

    session_id: str
    path: Path
    reader: IncrementalReader


@dataclass
class FileWatcher:
    """Watches multiple files for changes and reads new JSONL lines incrementally.

    Uses watchfiles library for cross-platform file change detection
    (inotify on Linux, kqueue on macOS).
    """

    on_lines_callback: Callable[[str, list[dict]], Awaitable[None]]
    on_file_deleted_callback: Callable[[str], Awaitable[None]] | None = None

    _watched_files: dict[str, WatchedFile] = field(default_factory=dict)
    _path_to_session: dict[Path, str] = field(default_factory=dict)
    _running: bool = False
    _watch_task: asyncio.Task | None = field(default=None, repr=False)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def add(self, session_id: str, path: Path, start_position: int = 0) -> None:
        """Add a file to the watch list.

        Args:
            session_id: Unique identifier for this session.
            path: Path to the JSONL file to watch.
            start_position: Byte offset to start reading from.

        Note:
            If watching is already started, the new file will be picked up
            on the next watch iteration.
        """
        reader = IncrementalReader(path=path, position=start_position)
        watched = WatchedFile(session_id=session_id, path=path, reader=reader)

        self._watched_files[session_id] = watched
        self._path_to_session[path.resolve()] = session_id

    def remove(self, session_id: str) -> None:
        """Remove a file from the watch list.

        Args:
            session_id: Identifier of the session to stop watching.
        """
        if session_id in self._watched_files:
            watched = self._watched_files[session_id]
            resolved_path = watched.path.resolve()
            del self._watched_files[session_id]
            if resolved_path in self._path_to_session:
                del self._path_to_session[resolved_path]

    def get_position(self, session_id: str) -> int | None:
        """Get the current read position for a session.

        Args:
            session_id: Identifier of the session.

        Returns:
            Current byte position, or None if session not found.
        """
        if session_id in self._watched_files:
            return self._watched_files[session_id].reader.position
        return None

    @property
    def is_running(self) -> bool:
        """Return whether the watcher is currently running."""
        return self._running

    @property
    def watched_sessions(self) -> list[str]:
        """Return list of session IDs being watched."""
        return list(self._watched_files.keys())

    async def start(self) -> None:
        """Start watching all registered files for changes.

        This is a non-blocking call that starts the watch loop in the background.
        Use stop() to cleanly shut down the watcher.
        """
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._watch_task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        """Stop watching files and clean up.

        Waits for the watch loop to terminate gracefully.
        """
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._watch_task:
            # Cancel the task and wait for it
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            self._watch_task = None

    async def _watch_loop(self) -> None:
        """Main watch loop that monitors files for changes."""
        while self._running:
            if not self._watched_files:
                # No files to watch, sleep briefly and check again
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=0.1
                    )
                    break  # Stop event was set
                except asyncio.TimeoutError:
                    continue

            # Get unique parent directories to watch
            watch_paths = set()
            for watched in self._watched_files.values():
                # Watch the parent directory, not the file itself
                # This allows us to detect file creation/deletion
                parent = watched.path.parent.resolve()
                watch_paths.add(parent)

            try:
                # Use awatch with a short debounce for responsiveness
                async for changes in awatch(
                    *watch_paths,
                    stop_event=self._stop_event,
                    debounce=100,  # 100ms debounce
                    recursive=False,
                ):
                    if not self._running:
                        break

                    await self._handle_changes(changes)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in watch loop: {e}")
                # Brief sleep before retrying
                await asyncio.sleep(0.5)

    async def _handle_changes(self, changes: set[tuple[Change, str]]) -> None:
        """Handle a batch of file change events.

        Args:
            changes: Set of (change_type, path) tuples from watchfiles.
        """
        # Group changes by session to batch process
        sessions_to_process: set[str] = set()
        deleted_sessions: set[str] = set()

        for change_type, path_str in changes:
            resolved_path = Path(path_str).resolve()

            if resolved_path not in self._path_to_session:
                continue

            session_id = self._path_to_session[resolved_path]

            if change_type == Change.deleted:
                deleted_sessions.add(session_id)
            elif change_type in (Change.modified, Change.added):
                sessions_to_process.add(session_id)

        # Process deletions first
        for session_id in deleted_sessions:
            if session_id in self._watched_files:
                self.remove(session_id)
                if self.on_file_deleted_callback:
                    try:
                        await self.on_file_deleted_callback(session_id)
                    except Exception as e:
                        logger.error(f"Error in file deleted callback: {e}")

        # Process modifications
        for session_id in sessions_to_process:
            if session_id not in self._watched_files:
                continue

            watched = self._watched_files[session_id]
            try:
                lines, new_position = watched.reader.read_new_lines()
                if lines:
                    await self.on_lines_callback(session_id, lines)
            except Exception as e:
                logger.error(f"Error processing changes for {session_id}: {e}")

    async def process_initial(self, session_id: str, last_n_lines: int = 3) -> None:
        """Process the last N lines of a newly added file.

        Call this after add() to get initial context for a new watch.

        Args:
            session_id: Identifier of the session to process.
            last_n_lines: Number of lines from the end to process.
        """
        if session_id not in self._watched_files:
            return

        watched = self._watched_files[session_id]
        watched.reader.seek_to_last_n_lines(last_n_lines)

        lines, _ = watched.reader.read_new_lines()
        if lines:
            await self.on_lines_callback(session_id, lines)
