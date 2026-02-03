"""WatcherService class integrating all watcher components.

This module provides the main orchestration service that wires together:
- ConfigManager: persistent session configuration
- StateManager: processing state persistence
- DestinationManager: messaging destination lifecycle
- FileWatcher: file change detection
- Transformer: line-to-event processing
- EventBufferManager: per-session event buffering
- SSEManager: SSE event broadcasting
- WatcherAPI: HTTP API endpoints
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

from claude_session_player.events import ProcessingContext
from claude_session_player.watcher.api import WatcherAPI
from claude_session_player.watcher.config import ConfigManager
from claude_session_player.watcher.destinations import DestinationManager
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.file_watcher import FileWatcher
from claude_session_player.watcher.sse import SSEManager
from claude_session_player.watcher.state import SessionState, StateManager
from claude_session_player.watcher.transformer import transform

if TYPE_CHECKING:
    from aiohttp.web import AppRunner, TCPSite

logger = logging.getLogger(__name__)


@dataclass
class WatcherService:
    """Main service orchestrating all watcher components.

    Handles lifecycle management (startup, shutdown) and event flow coordination
    between file watcher, transformer, event buffer, and SSE manager.
    """

    config_path: Path
    state_dir: Path

    # Injected components (for testability)
    config_manager: ConfigManager | None = None
    state_manager: StateManager | None = None
    destination_manager: DestinationManager | None = None
    file_watcher: FileWatcher | None = None
    event_buffer: EventBufferManager | None = None
    sse_manager: SSEManager | None = None
    api: WatcherAPI | None = None

    # HTTP server config
    host: str = "127.0.0.1"
    port: int = 8080

    # Internal state
    _runner: AppRunner | None = field(default=None, repr=False)
    _site: TCPSite | None = field(default=None, repr=False)
    _running: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize components if not injected."""
        # Create components if not provided (allows dependency injection for testing)
        if self.config_manager is None:
            self.config_manager = ConfigManager(self.config_path)

        if self.state_manager is None:
            self.state_manager = StateManager(self.state_dir)

        if self.event_buffer is None:
            self.event_buffer = EventBufferManager()

        if self.sse_manager is None:
            self.sse_manager = SSEManager(event_buffer=self.event_buffer)

        if self.file_watcher is None:
            self.file_watcher = FileWatcher(
                on_lines_callback=self._on_file_change,
                on_file_deleted_callback=self._on_file_deleted,
            )

        if self.destination_manager is None:
            self.destination_manager = DestinationManager(
                _config=self.config_manager,
                _on_session_start=self._on_destination_session_start,
                _on_session_stop=self._on_destination_session_stop,
            )

        if self.api is None:
            self.api = WatcherAPI(
                config_manager=self.config_manager,
                destination_manager=self.destination_manager,
                event_buffer=self.event_buffer,
                sse_manager=self.sse_manager,
            )

    @property
    def is_running(self) -> bool:
        """Return whether the service is currently running."""
        return self._running

    async def start(self) -> None:
        """Start the watcher service.

        Startup sequence:
        1. Load config.yaml
        2. For each session in config:
           - Load state (or create fresh if missing/corrupt)
           - Validate file exists (remove from config if not)
           - Add to FileWatcher with saved position
        3. Start FileWatcher
        4. Start HTTP server
        """
        if self._running:
            logger.warning("Service already running")
            return

        logger.info("Starting watcher service...")

        # Load existing config and resume sessions
        await self._load_and_resume_sessions()

        # Start file watcher
        await self.file_watcher.start()
        logger.info("File watcher started")

        # Start HTTP server
        app = self.api.create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        self._running = True
        logger.info(f"HTTP server listening on http://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the watcher service gracefully.

        Shutdown sequence:
        1. Stop accepting new HTTP connections
        2. Stop FileWatcher
        3. Save all session states
        4. Send session_ended to all SSE clients
        5. Close all SSE connections
        6. Exit
        """
        if not self._running:
            return

        logger.info("Stopping watcher service...")

        # Stop HTTP server first
        if self._site:
            await self._site.stop()
            self._site = None

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        logger.info("HTTP server stopped")

        # Stop file watcher
        await self.file_watcher.stop()
        logger.info("File watcher stopped")

        # Save all session states
        await self._save_all_states()
        logger.info("All states saved")

        # Shutdown destination manager (cancel keep-alive tasks)
        await self.destination_manager.shutdown()
        logger.info("Destination manager shutdown")

        # Close all SSE connections (send session_ended)
        sessions = self.config_manager.list_all()
        for session in sessions:
            await self.sse_manager.close_session(session.session_id, reason="shutdown")

        logger.info("All SSE connections closed")

        self._running = False
        logger.info("Watcher service stopped")

    async def watch(self, session_id: str, path: Path) -> None:
        """Add a session to be watched.

        This is a higher-level method that coordinates all components.
        The API layer uses this indirectly through its own handlers.

        Args:
            session_id: Unique identifier for the session.
            path: Absolute path to the session JSONL file.

        Raises:
            ValueError: If session_id already exists or path is invalid.
            FileNotFoundError: If path does not exist.
        """
        # Validate
        if not path.is_absolute():
            raise ValueError(f"Path must be absolute: {path}")
        if not path.exists():
            raise FileNotFoundError(f"Session file not found: {path}")

        # Check for duplicate
        if self.config_manager.get(session_id) is not None:
            raise ValueError(f"Session already exists: {session_id}")

        # Add to config
        self.config_manager.add(session_id, path)

        # Add to file watcher (start from end of file)
        file_size = path.stat().st_size
        self.file_watcher.add(session_id, path, start_position=file_size)

        # Process initial lines for context
        await self.file_watcher.process_initial(session_id, last_n_lines=3)

        logger.info(f"Now watching session: {session_id}")

    async def unwatch(self, session_id: str) -> None:
        """Stop watching a session.

        Coordinates cleanup across all components:
        1. Notify SSE subscribers
        2. Remove from file watcher
        3. Remove event buffer
        4. Delete state file
        5. Remove from config

        Args:
            session_id: Identifier of the session to stop watching.

        Raises:
            KeyError: If session_id not found.
        """
        # Check if session exists
        if self.config_manager.get(session_id) is None:
            raise KeyError(f"Session not found: {session_id}")

        # Emit session_ended event to SSE subscribers
        await self.sse_manager.close_session(session_id, reason="unwatched")

        # Remove from file watcher
        self.file_watcher.remove(session_id)

        # Remove event buffer
        self.event_buffer.remove_buffer(session_id)

        # Delete state file
        self.state_manager.delete(session_id)

        # Remove from config
        self.config_manager.remove(session_id)

        logger.info(f"Stopped watching session: {session_id}")

    async def _load_and_resume_sessions(self) -> None:
        """Load config and resume watching existing sessions.

        For each session in config:
        - Load state (or create fresh if missing/corrupt)
        - Validate file exists (remove from config if not)
        - Add to FileWatcher with saved position
        """
        sessions = self.config_manager.list_all()
        sessions_to_remove: list[str] = []

        for session in sessions:
            session_id = session.session_id
            path = session.path

            # Validate file still exists
            if not path.exists():
                logger.warning(
                    f"Session file no longer exists, removing: {session_id} ({path})"
                )
                sessions_to_remove.append(session_id)
                continue

            # Load state (or create fresh)
            state = self.state_manager.load(session_id)
            if state is None:
                logger.info(f"No saved state for {session_id}, starting fresh")
                # Start from end of file for new sessions
                file_size = path.stat().st_size
                start_position = file_size
            else:
                logger.info(
                    f"Resuming {session_id} from position {state.file_position}"
                )
                start_position = state.file_position

            # Add to file watcher
            self.file_watcher.add(session_id, path, start_position=start_position)

        # Remove sessions with missing files
        for session_id in sessions_to_remove:
            try:
                self.config_manager.remove(session_id)
                self.state_manager.delete(session_id)
            except KeyError:
                pass

        logger.info(f"Loaded {len(sessions) - len(sessions_to_remove)} sessions")

    async def _save_all_states(self) -> None:
        """Save state for all active sessions."""
        sessions = self.config_manager.list_all()

        for session in sessions:
            session_id = session.session_id

            # Get current position from file watcher
            position = self.file_watcher.get_position(session_id)
            if position is None:
                continue

            # Load existing state to preserve context
            existing_state = self.state_manager.load(session_id)
            if existing_state is not None:
                context = existing_state.processing_context
                line_number = existing_state.line_number
            else:
                context = ProcessingContext()
                line_number = 0

            # Create updated state
            state = SessionState(
                file_position=position,
                line_number=line_number,
                processing_context=context,
                last_modified=datetime.now(timezone.utc),
            )

            self.state_manager.save(session_id, state)

    async def _on_file_change(self, session_id: str, lines: list[dict]) -> None:
        """Handle file change callback from FileWatcher.

        Event flow:
        1. StateManager.load(session_id) → context
        2. transform(lines, context) → events, new_context
        3. StateManager.save(session_id, new_state)
        4. for event in events:
               EventBufferManager.add_event(session_id, event)
               SSEManager.broadcast(session_id, event_id, event)

        Args:
            session_id: The session that changed.
            lines: New parsed JSONL lines.
        """
        if not lines:
            return

        # Load existing state/context
        state = self.state_manager.load(session_id)
        if state is not None:
            context = state.processing_context
            line_number = state.line_number
        else:
            context = ProcessingContext()
            line_number = 0

        # Transform lines to events
        events, new_context = transform(lines, context)

        # Get current position from file watcher
        position = self.file_watcher.get_position(session_id)
        if position is None:
            position = 0

        # Update line number
        new_line_number = line_number + len(lines)

        # Save updated state
        new_state = SessionState(
            file_position=position,
            line_number=new_line_number,
            processing_context=new_context,
            last_modified=datetime.now(timezone.utc),
        )
        self.state_manager.save(session_id, new_state)

        # Buffer events and broadcast to SSE subscribers
        for event in events:
            event_id = self.event_buffer.add_event(session_id, event)
            await self.sse_manager.broadcast(session_id, event_id, event)

    async def _on_file_deleted(self, session_id: str) -> None:
        """Handle file deletion callback from FileWatcher.

        When a file is deleted:
        1. Emit session_ended event to SSE subscribers
        2. Remove from config
        3. Delete state file
        4. Remove event buffer

        Args:
            session_id: The session whose file was deleted.
        """
        logger.warning(f"Session file deleted: {session_id}")

        # Notify SSE subscribers
        await self.sse_manager.close_session(session_id, reason="file_deleted")

        # Remove event buffer
        self.event_buffer.remove_buffer(session_id)

        # Delete state file
        self.state_manager.delete(session_id)

        # Remove from config
        try:
            self.config_manager.remove(session_id)
        except KeyError:
            pass

    async def _on_destination_session_start(self, session_id: str, path: Path) -> None:
        """Handle session start callback from DestinationManager.

        Called when the first destination is attached to a session.
        Starts file watching for the session.

        Args:
            session_id: The session to start watching.
            path: Path to the session JSONL file.
        """
        logger.info(f"Starting file watching for session: {session_id}")

        # Add to config if not already present
        if self.config_manager.get(session_id) is None:
            self.config_manager.add(session_id, path)

        # Add to file watcher (start from end of file)
        file_size = path.stat().st_size
        self.file_watcher.add(session_id, path, start_position=file_size)

        # Process initial lines for context
        await self.file_watcher.process_initial(session_id, last_n_lines=3)

    async def _on_destination_session_stop(self, session_id: str) -> None:
        """Handle session stop callback from DestinationManager.

        Called when the keep-alive timer expires after the last destination
        detaches from a session. Stops file watching and cleans up.

        Args:
            session_id: The session to stop watching.
        """
        logger.info(f"Stopping file watching for session: {session_id}")

        # Emit session_ended event to SSE subscribers
        await self.sse_manager.close_session(session_id, reason="no_destinations")

        # Remove from file watcher
        self.file_watcher.remove(session_id)

        # Remove event buffer
        self.event_buffer.remove_buffer(session_id)

        # Delete state file
        self.state_manager.delete(session_id)

        # Note: config is not removed - session info persists
