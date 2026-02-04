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
- TelegramPublisher: Telegram Bot API integration
- SlackPublisher: Slack Web API integration
- RenderCache: pre-rendered session content caching
- MessageBindingManager: message-to-destination bindings
- MessageDebouncer: rate-limiting message updates
- SQLiteSessionIndexer: SQLite-backed session indexing
- SearchEngine: session search and ranking
- SearchStateManager: pagination state for bot commands
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

from claude_session_player.events import Event, ProcessingContext
from claude_session_player.watcher.api import WatcherAPI
from claude_session_player.watcher.config import ConfigManager
from claude_session_player.watcher.debouncer import MessageDebouncer
from claude_session_player.watcher.destinations import AttachedDestination, DestinationManager
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.file_watcher import FileWatcher
from claude_session_player.watcher.indexer import IndexConfig, SessionIndexer, SQLiteSessionIndexer
from claude_session_player.watcher.message_binding import MessageBinding, MessageBindingManager
from claude_session_player.watcher.rate_limit import RateLimiter
from claude_session_player.watcher.render_cache import RenderCache
from claude_session_player.watcher.search import SearchEngine
from claude_session_player.watcher.search_state import SearchStateManager
from claude_session_player.watcher.slack_publisher import SlackError, SlackPublisher
from claude_session_player.watcher.sse import SSEManager
from claude_session_player.watcher.state import SessionState, StateManager
from claude_session_player.watcher.telegram_publisher import TelegramError, TelegramPublisher
from claude_session_player.watcher.transformer import transform

if TYPE_CHECKING:
    from aiohttp.web import AppRunner, TCPSite

logger = logging.getLogger(__name__)


@dataclass
class WatcherService:
    """Main service orchestrating all watcher components.

    Handles lifecycle management (startup, shutdown) and event flow coordination
    between file watcher, transformer, event buffer, SSE manager, and messaging
    publishers (Telegram, Slack).
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

    # Messaging components (optional, created based on bot config)
    telegram_publisher: TelegramPublisher | None = None
    slack_publisher: SlackPublisher | None = None
    message_debouncer: MessageDebouncer | None = None

    # Single-message rendering components
    render_cache: RenderCache | None = None
    message_bindings: MessageBindingManager | None = None

    # Search components
    indexer: SessionIndexer | None = None
    sqlite_indexer: SQLiteSessionIndexer | None = None
    search_engine: SearchEngine | None = None
    search_state_manager: SearchStateManager | None = None

    # HTTP server config
    host: str = "127.0.0.1"
    port: int = 8080

    # Internal state
    _runner: AppRunner | None = field(default=None, repr=False)
    _site: TCPSite | None = field(default=None, repr=False)
    _running: bool = field(default=False, repr=False)
    _refresh_task: asyncio.Task | None = field(default=None, repr=False)
    _checkpoint_task: asyncio.Task | None = field(default=None, repr=False)
    _backup_task: asyncio.Task | None = field(default=None, repr=False)
    _start_time: datetime | None = field(default=None, repr=False)

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

        # Initialize messaging components based on bot config
        bot_config = self.config_manager.get_bot_config()

        if self.telegram_publisher is None and bot_config.telegram_token:
            self.telegram_publisher = TelegramPublisher(token=bot_config.telegram_token)

        if self.slack_publisher is None and bot_config.slack_token:
            self.slack_publisher = SlackPublisher(token=bot_config.slack_token)

        # Always create debouncer (works without publishers)
        if self.message_debouncer is None:
            self.message_debouncer = MessageDebouncer()

        # Initialize single-message rendering components
        if self.render_cache is None:
            self.render_cache = RenderCache()

        if self.message_bindings is None:
            self.message_bindings = MessageBindingManager()

        # Initialize search components
        index_config = self.config_manager.get_index_config()
        search_config = self.config_manager.get_search_config()
        db_config = self.config_manager.get_database_config()

        # Convert IndexConfig from config module to indexer IndexConfig
        indexer_config = IndexConfig(
            refresh_interval=index_config.refresh_interval,
            max_sessions_per_project=index_config.max_sessions_per_project,
            include_subagents=index_config.include_subagents,
            persist=index_config.persist,
        )

        # Create legacy indexer for backward compatibility if needed
        if self.indexer is None:
            self.indexer = SessionIndexer(
                paths=index_config.expand_paths(),
                config=indexer_config,
                state_dir=self.state_dir,
            )

        # Create SQLite-backed indexer for persistent search
        if self.sqlite_indexer is None:
            self.sqlite_indexer = SQLiteSessionIndexer(
                paths=index_config.expand_paths(),
                state_dir=db_config.get_state_dir(),
                config=indexer_config,
            )

        if self.search_engine is None:
            self.search_engine = SearchEngine(self.indexer)

        if self.search_state_manager is None:
            self.search_state_manager = SearchStateManager(
                ttl_seconds=search_config.state_ttl_seconds
            )

        # Create rate limiters for search endpoints
        search_limiter = RateLimiter(rate=30, window_seconds=60)  # 30/min per IP
        preview_limiter = RateLimiter(rate=60, window_seconds=60)  # 60/min per IP
        refresh_limiter = RateLimiter(rate=1, window_seconds=60)  # 1/60s global

        if self.api is None:
            self.api = WatcherAPI(
                config_manager=self.config_manager,
                destination_manager=self.destination_manager,
                event_buffer=self.event_buffer,
                sse_manager=self.sse_manager,
                indexer=self.indexer,
                sqlite_indexer=self.sqlite_indexer,
                search_engine=self.search_engine,
                search_limiter=search_limiter,
                preview_limiter=preview_limiter,
                refresh_limiter=refresh_limiter,
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
        3. Restore messaging destinations from config
        4. Initialize SQLite indexer and build/update index
        5. Optionally vacuum database on startup
        6. Start periodic index refresh
        7. Start periodic WAL checkpoint (if configured)
        8. Start periodic backup (if enabled)
        9. Start FileWatcher
        10. Start HTTP server
        """
        if self._running:
            logger.warning("Service already running")
            return

        logger.info("Starting watcher service...")
        self._start_time = datetime.now(timezone.utc)

        # Load existing config and resume sessions
        await self._load_and_resume_sessions()

        # Restore messaging destinations from config
        await self.destination_manager.restore_from_config()
        logger.info("Messaging destinations restored from config")

        # Initialize SQLite indexer
        if self.sqlite_indexer:
            try:
                await self.sqlite_indexer.initialize()
                logger.info("SQLite indexer initialized")

                # Check if index needs to be built
                stats = await self.sqlite_indexer.get_stats()
                if stats["total_sessions"] == 0:
                    logger.info("Building initial search index...")
                    count = await self.sqlite_indexer.build_full_index()
                    logger.info(f"Indexed {count} sessions")
                else:
                    logger.info(
                        f"Search index loaded: {stats['total_sessions']} sessions "
                        f"from {stats['total_projects']} projects"
                    )

                # Vacuum on startup if configured
                db_config = self.config_manager.get_database_config()
                if db_config.vacuum_on_startup:
                    await self.sqlite_indexer.db.vacuum()
                    logger.info("Database vacuum completed on startup")
            except Exception as e:
                logger.error(f"Failed to initialize SQLite indexer: {e}")
                await self._handle_index_error(e)

        # Build legacy index for backward compatibility
        if self.indexer:
            try:
                index = await self.indexer.get_index()
                logger.info(
                    f"Legacy indexer: {len(index.sessions)} sessions "
                    f"from {len(index.projects)} projects"
                )
            except Exception as e:
                logger.error(f"Failed to build legacy index: {e}")

        # Start periodic refresh task
        self._refresh_task = asyncio.create_task(self._periodic_refresh())
        logger.info("Periodic index refresh started")

        # Start checkpoint task if configured
        db_config = self.config_manager.get_database_config()
        if db_config.checkpoint_interval > 0:
            self._checkpoint_task = asyncio.create_task(self._periodic_checkpoint())
            logger.info(f"Periodic checkpoint started (interval: {db_config.checkpoint_interval}s)")

        # Start backup task if enabled
        if db_config.backup.enabled:
            self._backup_task = asyncio.create_task(self._periodic_backup())
            logger.info("Periodic backup started")

        # Start file watcher
        await self.file_watcher.start()
        logger.info("File watcher started")

        # Start render cache eviction task
        if self.render_cache:
            await self.render_cache.start()
            logger.info("Render cache eviction task started")

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
        2. Cancel periodic refresh task
        3. Cancel periodic checkpoint task
        4. Cancel periodic backup task
        5. Flush pending message updates
        6. Close messaging publishers
        7. Stop FileWatcher
        8. Save all session states
        9. Final database checkpoint before close
        10. Close SQLite indexer
        11. Send session_ended to all SSE clients
        12. Close all SSE connections
        13. Exit
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

        # Cancel all background tasks
        for task_name, task in [
            ("refresh", self._refresh_task),
            ("checkpoint", self._checkpoint_task),
            ("backup", self._backup_task),
        ]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logger.info(f"Periodic {task_name} task cancelled")

        self._refresh_task = None
        self._checkpoint_task = None
        self._backup_task = None

        # Flush pending message updates
        if self.message_debouncer:
            await self.message_debouncer.flush()
            logger.info("Message debouncer flushed")

        # Close messaging publishers
        if self.telegram_publisher:
            await self.telegram_publisher.close()
            logger.info("Telegram publisher closed")

        if self.slack_publisher:
            await self.slack_publisher.close()
            logger.info("Slack publisher closed")

        # Stop file watcher
        await self.file_watcher.stop()
        logger.info("File watcher stopped")

        # Stop render cache eviction task
        if self.render_cache:
            await self.render_cache.stop()
            logger.info("Render cache stopped")

        # Save all session states
        await self._save_all_states()
        logger.info("All states saved")

        # Final checkpoint and close SQLite indexer
        if self.sqlite_indexer:
            try:
                await self.sqlite_indexer.db.checkpoint()
                logger.info("Final WAL checkpoint completed")
            except Exception as e:
                logger.warning(f"Final checkpoint failed: {e}")

            await self.sqlite_indexer.close()
            logger.info("SQLite indexer closed")

        # Shutdown destination manager (cancel keep-alive tasks)
        await self.destination_manager.shutdown()
        logger.info("Destination manager shutdown")

        # Close all SSE connections (send session_ended)
        sessions = self.config_manager.list_all()
        for session in sessions:
            await self.sse_manager.close_session(session.session_id, reason="shutdown")

        logger.info("All SSE connections closed")

        self._running = False
        self._start_time = None
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
               Publish to messaging destinations

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

        # Rebuild render cache with all buffered events
        if self.render_cache and self.message_bindings:
            all_events_with_ids = self.event_buffer.get_events_since(session_id, None)
            all_events = [evt for _, evt in all_events_with_ids]
            self.render_cache.rebuild(session_id, all_events)

            # Push cached content to all bindings for this session
            await self._push_to_bindings(session_id)

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

    # -------------------------------------------------------------------------
    # Single-Message Rendering Methods
    # -------------------------------------------------------------------------

    async def _push_to_bindings(self, session_id: str) -> None:
        """Push cached render content to all bindings for a session.

        For each binding:
        1. Get cached content for the binding's preset
        2. Schedule debounced update with change detection

        Args:
            session_id: The session identifier.
        """
        if not self.render_cache or not self.message_bindings or not self.message_debouncer:
            return

        bindings = self.message_bindings.get_bindings_for_session(session_id)
        if not bindings:
            return

        for binding in bindings:
            content = self.render_cache.get(session_id, binding.preset)
            if content is None:
                continue

            # Schedule debounced update with change detection
            await self._push_binding_content(binding, content)

    async def _push_binding_content(self, binding: MessageBinding, content: str) -> None:
        """Push content to a single binding through the debouncer.

        Args:
            binding: The message binding to push to.
            content: The pre-rendered content to push.
        """
        if not self.message_debouncer:
            return

        from claude_session_player.watcher.destinations import parse_telegram_identifier

        dest = binding.destination

        async def do_update() -> None:
            try:
                if dest.type == "telegram" and self.telegram_publisher:
                    chat_id, _ = parse_telegram_identifier(dest.identifier)
                    await self.telegram_publisher.update_session_message(
                        chat_id=chat_id,
                        message_id=int(binding.message_id),
                        content=content,
                    )
                elif dest.type == "slack" and self.slack_publisher:
                    await self.slack_publisher.update_session_message(
                        channel=dest.identifier,
                        ts=binding.message_id,
                        content=content,
                    )

                # Update last_content in binding after successful push
                if self.message_bindings:
                    self.message_bindings.update_last_content(
                        binding.session_id, dest, content
                    )
            except (TelegramError, SlackError) as e:
                logger.warning(
                    "Failed to push binding content",
                    extra={
                        "session_id": binding.session_id,
                        "destination_type": dest.type,
                        "message_id": binding.message_id,
                        "error": str(e),
                    },
                )

        await self.message_debouncer.schedule_update(
            destination_type=dest.type,
            identifier=dest.identifier,
            message_id=binding.message_id,
            update_fn=do_update,
            content=content,  # String for change detection
        )

    async def create_session_binding(
        self,
        session_id: str,
        destination: AttachedDestination,
        preset: str = "desktop",
    ) -> str | None:
        """Create a new session message and binding.

        Creates an initial message with the current session state and
        creates a binding to track updates to that message.

        Args:
            session_id: The session identifier.
            destination: The destination to create the message in.
            preset: Display preset ("desktop" or "mobile").

        Returns:
            The message ID if successful, None if failed.
        """
        from claude_session_player.watcher.destinations import parse_telegram_identifier

        if not self.render_cache or not self.message_bindings:
            return None

        # Get or build initial content
        content = self.render_cache.get(session_id, preset)  # type: ignore[arg-type]
        if content is None:
            # Build cache if not present (e.g., first attach)
            all_events_with_ids = self.event_buffer.get_events_since(session_id, None)
            all_events = [evt for _, evt in all_events_with_ids]
            self.render_cache.rebuild(session_id, all_events)
            content = self.render_cache.get(session_id, preset)  # type: ignore[arg-type]

        # Create initial message
        message_id: str | None = None
        try:
            if destination.type == "telegram" and self.telegram_publisher:
                chat_id, thread_id = parse_telegram_identifier(destination.identifier)
                msg_id_int = await self.telegram_publisher.send_session_message(
                    chat_id=chat_id,
                    content=content or "",
                    thread_id=thread_id,
                )
                message_id = str(msg_id_int)

            elif destination.type == "slack" and self.slack_publisher:
                ts = await self.slack_publisher.send_session_message(
                    channel=destination.identifier,
                    content=content or "",
                )
                message_id = ts

        except (TelegramError, SlackError) as e:
            logger.warning(
                "Failed to create session message",
                extra={
                    "session_id": session_id,
                    "destination_type": destination.type,
                    "error": str(e),
                },
            )
            return None

        if not message_id:
            return None

        # Create binding
        binding = MessageBinding(
            session_id=session_id,
            preset=preset,  # type: ignore[arg-type]
            destination=destination,
            message_id=message_id,
            last_content=content or "",
        )
        self.message_bindings.add_binding(binding)

        logger.info(
            "Created session binding",
            extra={
                "session_id": session_id,
                "destination_type": destination.type,
                "message_id": message_id,
                "preset": preset,
            },
        )

        return message_id

    async def remove_session_binding(
        self,
        session_id: str,
        destination: AttachedDestination,
    ) -> bool:
        """Remove a session binding.

        Removes the binding and clears debouncer state for the message.

        Args:
            session_id: The session identifier.
            destination: The destination to unbind.

        Returns:
            True if binding was removed, False if not found.
        """
        if not self.message_bindings or not self.message_debouncer:
            return False

        binding = self.message_bindings.remove_binding(session_id, destination)
        if not binding:
            return False

        # Clear debouncer state
        self.message_debouncer.clear_content(
            destination.type,
            destination.identifier,
            binding.message_id,
        )

        logger.info(
            "Removed session binding",
            extra={
                "session_id": session_id,
                "destination_type": destination.type,
                "message_id": binding.message_id,
            },
        )

        return True

    async def _periodic_refresh(self) -> None:
        """Background task for periodic index refresh.

        Runs continuously, refreshing both legacy and SQLite indexes
        at the configured interval. Errors are logged but do not crash the service.
        """
        index_config = self.config_manager.get_index_config()
        interval = index_config.refresh_interval

        while True:
            try:
                await asyncio.sleep(interval)

                start = time.monotonic()

                # Refresh SQLite index (incremental update)
                if self.sqlite_indexer:
                    try:
                        added, updated, removed = await self.sqlite_indexer.incremental_update()
                        duration = time.monotonic() - start

                        if added or updated or removed:
                            logger.info(
                                f"Index updated in {duration:.2f}s: "
                                f"+{added}, ~{updated}, -{removed}"
                            )
                        else:
                            logger.debug(f"Index check in {duration:.2f}s: no changes")
                    except Exception as e:
                        logger.error(f"SQLite index refresh failed: {e}")
                        await self._handle_index_error(e)

                # Also refresh legacy index for backward compatibility
                if self.indexer:
                    try:
                        await self.indexer.refresh(force=True)
                    except Exception as e:
                        logger.debug(f"Legacy index refresh failed: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Index refresh failed: {e}")
                # Continue running, try again next interval

    async def _periodic_checkpoint(self) -> None:
        """Background task for WAL checkpoint.

        Periodically checkpoints the SQLite database to reduce WAL file size
        and improve read performance.
        """
        db_config = self.config_manager.get_database_config()
        interval = db_config.checkpoint_interval

        while True:
            try:
                await asyncio.sleep(interval)

                if self.sqlite_indexer:
                    await self.sqlite_indexer.db.checkpoint()
                    logger.debug("WAL checkpoint completed")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"WAL checkpoint failed: {e}")

    async def _periodic_backup(self) -> None:
        """Background task for automated backups.

        Creates daily backups of the search database and rotates old ones.
        """
        # Run once per day (86400 seconds)
        interval = 86400

        while True:
            try:
                await asyncio.sleep(interval)
                await self._create_backup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Backup failed: {e}")

    async def _create_backup(self) -> None:
        """Create a backup and rotate old ones."""
        if not self.sqlite_indexer:
            return

        db_config = self.config_manager.get_database_config()
        backup_dir = db_config.get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"search_{timestamp}.db"

        await self.sqlite_indexer.db.backup(backup_path)
        logger.info(f"Backup created: {backup_path}")

        # Rotate old backups
        keep_count = db_config.backup.keep_count
        backups = sorted(backup_dir.glob("search_*.db"), reverse=True)

        for old_backup in backups[keep_count:]:
            old_backup.unlink()
            logger.debug(f"Deleted old backup: {old_backup}")

    async def _handle_index_error(self, error: Exception) -> None:
        """Handle index-related errors.

        Attempts to recover from database corruption if detected.

        Args:
            error: The exception that occurred.
        """
        logger.error(f"Index error: {error}")

        if self.sqlite_indexer and "corrupt" in str(error).lower():
            logger.warning("Attempting database recovery...")
            try:
                await self.sqlite_indexer.db._recover_database()
                count = await self.sqlite_indexer.build_full_index()
                logger.info(f"Database recovered and rebuilt with {count} sessions")
            except Exception as recovery_error:
                logger.error(f"Database recovery failed: {recovery_error}")

    async def validate_destination(self, destination_type: str) -> None:
        """Validate bot credentials for a destination type.

        Args:
            destination_type: "telegram" or "slack".

        Raises:
            TelegramError: If Telegram validation fails.
            SlackError: If Slack validation fails.
            ValueError: If destination type not configured.
        """
        from claude_session_player.watcher.telegram_publisher import TelegramAuthError
        from claude_session_player.watcher.slack_publisher import SlackAuthError

        if destination_type == "telegram":
            if not self.telegram_publisher:
                raise TelegramAuthError("Telegram bot token not configured")
            await self.telegram_publisher.validate()

        elif destination_type == "slack":
            if not self.slack_publisher:
                raise SlackAuthError("Slack bot token not configured")
            await self.slack_publisher.validate()
