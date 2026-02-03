"""REST API for session watcher service.

Provides endpoints for watch/unwatch/list operations and delegates
SSE streaming to the SSE module.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from claude_session_player.watcher.config import ConfigManager
    from claude_session_player.watcher.event_buffer import EventBufferManager
    from claude_session_player.watcher.file_watcher import FileWatcher
    from claude_session_player.watcher.sse import SSEManager
    from claude_session_player.watcher.state import StateManager


@dataclass
class WatcherAPI:
    """REST API handler for session watcher service.

    Coordinates between ConfigManager, StateManager, FileWatcher, and SSEManager
    to provide a unified HTTP interface for managing watched sessions.
    """

    config_manager: ConfigManager
    state_manager: StateManager
    file_watcher: FileWatcher
    event_buffer: EventBufferManager
    sse_manager: SSEManager

    _start_time: float = field(default_factory=time.time, repr=False)

    async def handle_watch(self, request: web.Request) -> web.Response:
        """Handle POST /watch - add session to watch list.

        Request body:
            {
                "session_id": "014d9d94-abc123",
                "path": "/path/to/session.jsonl"
            }

        Response 201:
            {
                "session_id": "014d9d94-abc123",
                "status": "watching"
            }

        Response 400: Invalid request (missing fields, invalid path)
        Response 404: File not found
        Response 409: Session ID already exists
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"error": "Invalid JSON body"},
                status=400,
            )

        # Validate required fields
        session_id = data.get("session_id")
        path_str = data.get("path")

        if not session_id:
            return web.json_response(
                {"error": "Missing required field: session_id"},
                status=400,
            )

        if not path_str:
            return web.json_response(
                {"error": "Missing required field: path"},
                status=400,
            )

        path = Path(path_str)

        # Validate path is absolute
        if not path.is_absolute():
            return web.json_response(
                {"error": f"Path must be absolute: {path}"},
                status=400,
            )

        # Check if file exists
        if not path.exists():
            return web.json_response(
                {"error": f"File not found: {path}"},
                status=404,
            )

        # Check for duplicate session
        if self.config_manager.get(session_id) is not None:
            return web.json_response(
                {"error": f"Session already exists: {session_id}"},
                status=409,
            )

        # Add to config
        try:
            self.config_manager.add(session_id, path)
        except ValueError as e:
            return web.json_response(
                {"error": str(e)},
                status=400,
            )
        except FileNotFoundError as e:
            return web.json_response(
                {"error": str(e)},
                status=404,
            )

        # Add to file watcher (start from end of file)
        file_size = path.stat().st_size
        self.file_watcher.add(session_id, path, start_position=file_size)

        # Process initial lines for context
        await self.file_watcher.process_initial(session_id, last_n_lines=3)

        return web.json_response(
            {"session_id": session_id, "status": "watching"},
            status=201,
        )

    async def handle_unwatch(self, request: web.Request) -> web.Response:
        """Handle DELETE /unwatch/{session_id} - remove session.

        Response 204: Success (no body)
        Response 404: Session not found
        """
        session_id = request.match_info["session_id"]

        # Check if session exists
        if self.config_manager.get(session_id) is None:
            return web.json_response(
                {"error": f"Session not found: {session_id}"},
                status=404,
            )

        # Emit session_ended event to SSE subscribers
        await self.sse_manager.close_session(session_id, reason="unwatched")

        # Remove from file watcher
        self.file_watcher.remove(session_id)

        # Remove event buffer
        self.event_buffer.remove_buffer(session_id)

        # Delete state file
        self.state_manager.delete(session_id)

        # Remove from config
        try:
            self.config_manager.remove(session_id)
        except KeyError:
            # Already removed, not an error
            pass

        return web.Response(status=204)

    async def handle_list_sessions(self, request: web.Request) -> web.Response:
        """Handle GET /sessions - list all watched sessions.

        Response 200:
            {
                "sessions": [
                    {
                        "session_id": "014d9d94-abc123",
                        "path": "/path/to/session.jsonl",
                        "status": "watching",
                        "file_position": 12345,
                        "last_event_id": "evt_042"
                    }
                ]
            }
        """
        sessions = self.config_manager.list_all()
        result = []

        for session in sessions:
            session_id = session.session_id

            # Get file position from file watcher or state manager
            file_position = self.file_watcher.get_position(session_id)
            if file_position is None:
                # Try loading from state manager
                state = self.state_manager.load(session_id)
                file_position = state.file_position if state else 0

            # Get last event ID from buffer
            buffer = self.event_buffer.get_buffer(session_id)
            events = buffer.get_since(None)
            last_event_id = events[-1][0] if events else None

            result.append({
                "session_id": session_id,
                "path": str(session.path),
                "status": "watching",
                "file_position": file_position,
                "last_event_id": last_event_id,
            })

        return web.json_response({"sessions": result})

    async def handle_session_events(self, request: web.Request) -> web.StreamResponse:
        """Handle GET /sessions/{session_id}/events - SSE stream.

        Delegates to SSE module for event streaming.

        Headers:
            Accept: text/event-stream
            Last-Event-ID: {event_id}  (optional, for replay)

        Response: SSE stream
        Response 404: Session not found
        """
        session_id = request.match_info["session_id"]

        # Check if session exists
        if self.config_manager.get(session_id) is None:
            return web.json_response(
                {"error": f"Session not found: {session_id}"},
                status=404,
            )

        # Get Last-Event-ID from headers
        last_event_id = request.headers.get("Last-Event-ID")

        # Create streaming response
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request)

        # Connect to SSE manager
        try:
            connection = await self.sse_manager.connect(
                session_id=session_id,
                response=response,
                last_event_id=last_event_id,
            )

            # Keep the connection open until client disconnects or session ends
            while not connection.is_closed:
                # Check if request is disconnected
                if request.transport is None or request.transport.is_closing():
                    break
                # Sleep briefly to avoid busy loop
                await asyncio.sleep(0.1)

        except ConnectionError:
            # Client disconnected
            pass
        finally:
            # Ensure cleanup
            if "connection" in locals():
                await self.sse_manager.disconnect(connection)

        return response

    async def handle_health(self, request: web.Request) -> web.Response:
        """Handle GET /health - health check.

        Response 200:
            {
                "status": "healthy",
                "sessions_watched": 42,
                "uptime_seconds": 3600
            }
        """
        sessions = self.config_manager.list_all()
        uptime = int(time.time() - self._start_time)

        return web.json_response({
            "status": "healthy",
            "sessions_watched": len(sessions),
            "uptime_seconds": uptime,
        })

    def create_app(self) -> web.Application:
        """Create and configure the aiohttp web application.

        Returns:
            Configured aiohttp Application with all routes registered.
        """
        app = web.Application()

        app.router.add_post("/watch", self.handle_watch)
        app.router.add_delete("/unwatch/{session_id}", self.handle_unwatch)
        app.router.add_get("/sessions", self.handle_list_sessions)
        app.router.add_get("/sessions/{session_id}/events", self.handle_session_events)
        app.router.add_get("/health", self.handle_health)

        return app
