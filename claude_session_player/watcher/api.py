"""REST API for session watcher service.

Provides endpoints for attach/detach/list operations and delegates
SSE streaming to the SSE module.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from claude_session_player.watcher.config import BotConfig, ConfigManager
    from claude_session_player.watcher.destinations import DestinationManager
    from claude_session_player.watcher.event_buffer import EventBufferManager
    from claude_session_player.watcher.sse import SSEManager


@dataclass
class WatcherAPI:
    """REST API handler for session watcher service.

    Coordinates between ConfigManager, DestinationManager, EventBufferManager,
    and SSEManager to provide a unified HTTP interface for managing watched
    sessions and messaging destinations.
    """

    config_manager: ConfigManager
    destination_manager: DestinationManager
    event_buffer: EventBufferManager
    sse_manager: SSEManager

    _start_time: float = field(default_factory=time.time, repr=False)

    async def handle_attach(self, request: web.Request) -> web.Response:
        """Handle POST /attach - attach a messaging destination to a session.

        Request body:
            {
                "session_id": "my-session",
                "path": "/path/to/session.jsonl",  # Required if session unknown
                "destination": {
                    "type": "telegram",  # or "slack"
                    "chat_id": "123456789",  # for telegram
                    "channel": "C0123456789"  # for slack
                },
                "replay_count": 0  # Optional, default 0
            }

        Response 201:
            {
                "attached": true,
                "session_id": "my-session",
                "destination": {"type": "telegram", "chat_id": "123456789"},
                "replayed_events": 0
            }

        Error responses:
        - 400: Invalid request (missing fields, invalid destination type)
        - 401: Bot token not configured
        - 403: Bot credential validation failed
        - 404: Session path not found
        """
        # Import here to avoid circular imports at module load time
        from claude_session_player.watcher.slack_publisher import SlackAuthError
        from claude_session_player.watcher.telegram_publisher import TelegramAuthError

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        # Validate required fields
        session_id = data.get("session_id")
        if not session_id:
            return web.json_response({"error": "session_id required"}, status=400)

        destination = data.get("destination")
        if not destination:
            return web.json_response({"error": "destination required"}, status=400)

        dest_type = destination.get("type")
        if dest_type not in ("telegram", "slack"):
            return web.json_response(
                {"error": "destination.type must be 'telegram' or 'slack'"},
                status=400,
            )

        # Validate destination fields
        if dest_type == "telegram":
            identifier = destination.get("chat_id")
            if not identifier:
                return web.json_response(
                    {"error": "destination.chat_id required for telegram"},
                    status=400,
                )
        else:
            identifier = destination.get("channel")
            if not identifier:
                return web.json_response(
                    {"error": "destination.channel required for slack"},
                    status=400,
                )

        path_str = data.get("path")
        path = Path(path_str) if path_str else None
        replay_count = data.get("replay_count", 0)

        # Validate path if provided
        if path is not None:
            if not path.is_absolute():
                return web.json_response(
                    {"error": f"Path must be absolute: {path}"},
                    status=400,
                )
            if not path.exists():
                return web.json_response(
                    {"error": f"Session path not found: {path}"},
                    status=404,
                )

        try:
            # Validate bot credentials before attaching
            await self._validate_destination(dest_type)

            # Attach destination
            await self.destination_manager.attach(
                session_id=session_id,
                path=path,
                destination_type=dest_type,
                identifier=identifier,
            )

            # Handle replay if requested
            replayed = 0
            if replay_count > 0:
                replayed = await self._replay_to_destination(
                    session_id=session_id,
                    destination_type=dest_type,
                    identifier=identifier,
                    count=replay_count,
                )

            # Build destination response based on type
            if dest_type == "telegram":
                dest_response = {"type": dest_type, "chat_id": identifier}
            else:
                dest_response = {"type": dest_type, "channel": identifier}

            return web.json_response(
                {
                    "attached": True,
                    "session_id": session_id,
                    "destination": dest_response,
                    "replayed_events": replayed,
                },
                status=201,
            )

        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except FileNotFoundError:
            return web.json_response(
                {"error": "Session path not found"},
                status=404,
            )
        except TelegramAuthError as e:
            error_msg = str(e)
            if "not configured" in error_msg.lower():
                return web.json_response(
                    {"error": "Telegram bot token not configured"},
                    status=401,
                )
            return web.json_response(
                {"error": "Telegram bot credential validation failed"},
                status=403,
            )
        except SlackAuthError as e:
            error_msg = str(e)
            if "not configured" in error_msg.lower():
                return web.json_response(
                    {"error": "Slack bot token not configured"},
                    status=401,
                )
            return web.json_response(
                {"error": "Slack bot credential validation failed"},
                status=403,
            )

    async def _validate_destination(self, dest_type: str) -> None:
        """Validate bot credentials for the destination type.

        Args:
            dest_type: "telegram" or "slack".

        Raises:
            TelegramAuthError: If Telegram bot token invalid or not configured.
            SlackAuthError: If Slack bot token invalid or not configured.
        """
        from claude_session_player.watcher.slack_publisher import (
            SlackAuthError,
            SlackPublisher,
        )
        from claude_session_player.watcher.telegram_publisher import (
            TelegramAuthError,
            TelegramPublisher,
        )

        bot_config = self.config_manager.get_bot_config()

        if dest_type == "telegram":
            if not bot_config.telegram_token:
                raise TelegramAuthError("Telegram bot token not configured")
            publisher = TelegramPublisher(token=bot_config.telegram_token)
            try:
                await publisher.validate()
            finally:
                await publisher.close()
        else:  # slack
            if not bot_config.slack_token:
                raise SlackAuthError("Slack bot token not configured")
            publisher = SlackPublisher(token=bot_config.slack_token)
            try:
                await publisher.validate()
            finally:
                await publisher.close()

    async def _replay_to_destination(
        self,
        session_id: str,
        destination_type: str,
        identifier: str,
        count: int,
    ) -> int:
        """Replay events to a destination.

        Args:
            session_id: Session identifier.
            destination_type: "telegram" or "slack".
            identifier: chat_id or channel.
            count: Number of events to replay.

        Returns:
            Number of events actually replayed.
        """
        # Get events from buffer
        buffer = self.event_buffer.get_buffer(session_id)
        events = buffer.get_since(None)

        # Limit to requested count (take last N)
        if len(events) > count:
            events = events[-count:]

        # TODO: In issue #76, this will be integrated with MessageStateTracker
        # to properly format and send replay messages. For now, just return count.
        return len(events)

    async def handle_detach(self, request: web.Request) -> web.Response:
        """Handle POST /detach - detach a messaging destination from a session.

        Request body:
            {
                "session_id": "my-session",
                "destination": {
                    "type": "telegram",
                    "chat_id": "123456789"
                }
            }

        Response 204: Success (no body)

        Error responses:
        - 400: Invalid request
        - 404: Session or destination not found
        """
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        session_id = data.get("session_id")
        destination = data.get("destination")

        if not session_id or not destination:
            return web.json_response(
                {"error": "session_id and destination required"},
                status=400,
            )

        dest_type = destination.get("type")
        if dest_type == "telegram":
            identifier = destination.get("chat_id")
        elif dest_type == "slack":
            identifier = destination.get("channel")
        else:
            return web.json_response(
                {"error": "Invalid destination type"},
                status=400,
            )

        if not identifier:
            return web.json_response(
                {"error": "Destination identifier required"},
                status=400,
            )

        detached = await self.destination_manager.detach(
            session_id=session_id,
            destination_type=dest_type,
            identifier=identifier,
        )

        if not detached:
            return web.json_response(
                {"error": "Destination not found"},
                status=404,
            )

        return web.Response(status=204)

    async def handle_list_sessions(self, request: web.Request) -> web.Response:
        """Handle GET /sessions - list all sessions and their destinations.

        Response 200:
            {
                "sessions": [
                    {
                        "session_id": "my-session",
                        "path": "/path/to/session.jsonl",
                        "sse_clients": 2,
                        "destinations": {
                            "telegram": [{"chat_id": "123456789"}],
                            "slack": [{"channel": "C0123456789"}]
                        }
                    }
                ]
            }
        """
        sessions = self.config_manager.list_all()
        result = []

        for session in sessions:
            session_id = session.session_id

            # Get SSE client count
            sse_clients = self.sse_manager.get_connection_count(session_id)

            # Get destinations
            destinations = self.destination_manager.get_destinations(session_id)
            telegram_dests = [
                {"chat_id": d.identifier}
                for d in destinations
                if d.type == "telegram"
            ]
            slack_dests = [
                {"channel": d.identifier}
                for d in destinations
                if d.type == "slack"
            ]

            result.append({
                "session_id": session_id,
                "path": str(session.path),
                "sse_clients": sse_clients,
                "destinations": {
                    "telegram": telegram_dests,
                    "slack": slack_dests,
                },
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
        """Handle GET /health - health check with bot status.

        Response 200:
            {
                "status": "healthy",
                "sessions_watched": 3,
                "uptime_seconds": 3600,
                "bots": {
                    "telegram": "configured",  # or "not_configured"
                    "slack": "not_configured"
                }
            }
        """
        sessions = self.config_manager.list_all()
        uptime = int(time.time() - self._start_time)
        bot_config = self.config_manager.get_bot_config()

        return web.json_response({
            "status": "healthy",
            "sessions_watched": len(sessions),
            "uptime_seconds": uptime,
            "bots": {
                "telegram": "configured" if bot_config.telegram_token else "not_configured",
                "slack": "configured" if bot_config.slack_token else "not_configured",
            },
        })

    def create_app(self) -> web.Application:
        """Create and configure the aiohttp web application.

        Returns:
            Configured aiohttp Application with all routes registered.
        """
        app = web.Application()

        app.router.add_post("/attach", self.handle_attach)
        app.router.add_post("/detach", self.handle_detach)
        app.router.add_get("/sessions", self.handle_list_sessions)
        app.router.add_get("/sessions/{session_id}/events", self.handle_session_events)
        app.router.add_get("/health", self.handle_health)

        return app
