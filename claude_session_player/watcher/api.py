"""REST API for session watcher service.

Provides endpoints for attach/detach/list operations and delegates
SSE streaming to the SSE module. Also provides search endpoints for
querying indexed sessions.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from claude_session_player.watcher.config import BotConfig, ConfigManager
    from claude_session_player.watcher.destinations import DestinationManager
    from claude_session_player.watcher.event_buffer import EventBufferManager
    from claude_session_player.watcher.indexer import SessionIndexer, SQLiteSessionIndexer
    from claude_session_player.watcher.rate_limit import RateLimiter
    from claude_session_player.watcher.search import SearchEngine
    from claude_session_player.watcher.sse import SSEManager

# Type alias for replay callback
ReplayCallback = Callable[[str, str, str, int], Awaitable[int]]


def _parse_iso_date(value: str | None) -> datetime | None:
    """Parse an ISO date string to datetime.

    Args:
        value: ISO date string or None.

    Returns:
        datetime with UTC timezone if valid, None otherwise.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


@dataclass
class WatcherAPI:
    """REST API handler for session watcher service.

    Coordinates between ConfigManager, DestinationManager, EventBufferManager,
    and SSEManager to provide a unified HTTP interface for managing watched
    sessions and messaging destinations.

    Also provides search endpoints when indexer and search_engine are configured.
    """

    config_manager: ConfigManager
    destination_manager: DestinationManager
    event_buffer: EventBufferManager
    sse_manager: SSEManager

    # Optional callback for replaying events (injected by WatcherService)
    replay_callback: ReplayCallback | None = None

    # Optional search components (injected by WatcherService)
    indexer: SessionIndexer | None = None
    sqlite_indexer: SQLiteSessionIndexer | None = None
    search_engine: SearchEngine | None = None

    # Rate limiters for search endpoints
    search_limiter: RateLimiter | None = None  # 30/min per IP
    preview_limiter: RateLimiter | None = None  # 60/min per IP
    refresh_limiter: RateLimiter | None = None  # 1/60s global

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
        # Use callback if provided (injected by WatcherService)
        if self.replay_callback:
            return await self.replay_callback(
                session_id, destination_type, identifier, count
            )

        # Fallback: just count available events without sending
        buffer = self.event_buffer.get_buffer(session_id)
        events = buffer.get_since(None)

        # Limit to requested count (take last N)
        if len(events) > count:
            events = events[-count:]

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
        """Handle GET /health - health check with bot and index status.

        Response 200:
            {
                "status": "healthy",
                "sessions_watched": 3,
                "sessions_indexed": 100,
                "projects_indexed": 5,
                "index_age_seconds": 127,
                "uptime_seconds": 3600,
                "bots": {
                    "telegram": "configured",  # or "not_configured"
                    "slack": "not_configured"
                },
                "index": {
                    "sessions": 100,
                    "projects": 5,
                    "fts_enabled": true,
                    "last_refresh": "2024-01-15T10:30:00Z"
                }
            }
        """
        sessions = self.config_manager.list_all()
        uptime = int(time.time() - self._start_time)
        bot_config = self.config_manager.get_bot_config()

        # Get index stats
        sessions_indexed = 0
        projects_indexed = 0
        index_age_seconds = 0
        index_stats: dict | None = None

        # Prefer SQLite indexer stats if available
        if self.sqlite_indexer is not None:
            try:
                stats = await self.sqlite_indexer.get_stats()
                sessions_indexed = stats.get("total_sessions", 0)
                projects_indexed = stats.get("total_projects", 0)
                index_stats = {
                    "sessions": sessions_indexed,
                    "projects": projects_indexed,
                    "fts_enabled": stats.get("fts_available", False),
                    "last_refresh": stats.get("last_incremental_index"),
                }
                # Calculate index age from last_incremental_index
                last_refresh = stats.get("last_incremental_index")
                if last_refresh:
                    try:
                        last_dt = datetime.fromisoformat(last_refresh)
                        index_age_seconds = int((datetime.now(timezone.utc) - last_dt).total_seconds())
                    except ValueError:
                        pass
            except Exception:
                pass  # Index not available

        # Fall back to legacy indexer if SQLite not available
        elif self.indexer is not None:
            try:
                index = await self.indexer.get_index()
                sessions_indexed = len(index.sessions)
                projects_indexed = len(index.projects)
                index_age_seconds = self._get_index_age_seconds()
            except Exception:
                pass  # Index not available

        response_data = {
            "status": "healthy",
            "sessions_watched": len(sessions),
            "sessions_indexed": sessions_indexed,
            "projects_indexed": projects_indexed,
            "index_age_seconds": index_age_seconds,
            "uptime_seconds": uptime,
            "bots": {
                "telegram": "configured" if bot_config.telegram_token else "not_configured",
                "slack": "configured" if bot_config.slack_token else "not_configured",
            },
        }

        # Add detailed index stats if available
        if index_stats:
            response_data["index"] = index_stats

        return web.json_response(response_data)

    # =========================================================================
    # Search Endpoints
    # =========================================================================

    def _get_client_ip(self, request: web.Request) -> str:
        """Get client IP for rate limiting.

        Args:
            request: The HTTP request.

        Returns:
            Client IP address string.
        """
        # Check X-Forwarded-For header first (for reverse proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain
            return forwarded.split(",")[0].strip()
        # Fall back to peer address
        peername = request.transport.get_extra_info("peername") if request.transport else None
        if peername:
            return peername[0]
        return "unknown"

    def _get_index_age_seconds(self) -> int:
        """Get the age of the search index in seconds.

        Returns:
            Seconds since last index refresh, or 0 if no index.
        """
        if self.indexer is None or self.indexer._index is None:
            return 0
        elapsed = datetime.now(timezone.utc) - self.indexer._index.last_refresh
        return int(elapsed.total_seconds())

    async def handle_search(self, request: web.Request) -> web.Response:
        """Handle GET /search - search sessions across all indexed projects.

        Query Parameters:
            q: Search query (optional)
            project: Project name filter (optional)
            since: ISO date filter (optional)
            until: ISO date filter (optional)
            sort: recent|oldest|size|duration (default: recent)
            limit: Results per page (max: 10, default: 5)
            offset: Pagination offset (default: 0)

        Response 200:
            {
                "query": "auth bug",
                "filters": {"project": null, "since": null, "until": null},
                "sort": "recent",
                "total": 3,
                "offset": 0,
                "limit": 5,
                "results": [...],
                "index_age_seconds": 127
            }

        Response 429: Rate limited
        """
        # Check if search is available
        if self.search_engine is None or self.indexer is None:
            return web.json_response(
                {"error": "Search not available"},
                status=503,
            )

        # Check rate limit
        if self.search_limiter:
            client_ip = self._get_client_ip(request)
            allowed, retry_after = self.search_limiter.check(f"api:{client_ip}")
            if not allowed:
                return web.json_response(
                    {
                        "error": "rate_limited",
                        "retry_after_seconds": retry_after,
                        "message": "Too many requests.",
                    },
                    status=429,
                )

        # Parse query parameters
        query = request.query.get("q", "")
        project = request.query.get("project")
        since_str = request.query.get("since")
        until_str = request.query.get("until")
        sort = request.query.get("sort", "recent")
        limit_str = request.query.get("limit", "5")
        offset_str = request.query.get("offset", "0")

        # Validate sort
        if sort not in ("recent", "oldest", "size", "duration"):
            sort = "recent"

        # Validate limit
        try:
            limit = int(limit_str)
            limit = max(1, min(10, limit))  # Clamp to 1-10
        except ValueError:
            limit = 5

        # Validate offset
        try:
            offset = int(offset_str)
            offset = max(0, offset)
        except ValueError:
            offset = 0

        # Parse dates
        since = _parse_iso_date(since_str)
        until = _parse_iso_date(until_str)

        # Build search params
        from claude_session_player.watcher.search import SearchFilters, SearchParams

        filters = SearchFilters(project=project, since=since, until=until)
        params = SearchParams(
            query=query,
            terms=query.split() if query else [],
            filters=filters,
            sort=sort,
            limit=limit,
            offset=offset,
        )

        # Execute search
        results = await self.search_engine.search(params)

        # Build response
        result_list = []
        for session in results.results:
            result_list.append({
                "session_id": session.session_id,
                "project": {
                    "display_name": session.project_display_name,
                    "encoded_name": session.project_encoded,
                    "decoded_path": str(Path(session.file_path).parent.parent)
                    if session.file_path
                    else None,
                },
                "summary": session.summary,
                "file_path": str(session.file_path),
                "created_at": session.created_at.isoformat(),
                "modified_at": session.modified_at.isoformat(),
                "duration_ms": session.duration_ms,
                "size_bytes": session.size_bytes,
                "line_count": session.line_count,
                "has_subagents": session.has_subagents,
                "match_score": 0.0,  # TODO: Include score from search_ranked
            })

        return web.json_response({
            "query": query,
            "filters": {
                "project": project,
                "since": since.isoformat() if since else None,
                "until": until.isoformat() if until else None,
            },
            "sort": sort,
            "total": results.total,
            "offset": offset,
            "limit": limit,
            "results": result_list,
            "index_age_seconds": self._get_index_age_seconds(),
        })

    async def handle_projects(self, request: web.Request) -> web.Response:
        """Handle GET /projects - list all indexed projects with session counts.

        Query Parameters:
            since: ISO date filter (optional)
            until: ISO date filter (optional)

        Response 200:
            {
                "projects": [...],
                "total_projects": 4,
                "total_sessions": 28,
                "index_age_seconds": 127
            }
        """
        # Check if search is available
        if self.indexer is None:
            return web.json_response(
                {"error": "Search not available"},
                status=503,
            )

        # Check rate limit (reuse search limiter)
        if self.search_limiter:
            client_ip = self._get_client_ip(request)
            allowed, retry_after = self.search_limiter.check(f"api:{client_ip}")
            if not allowed:
                return web.json_response(
                    {
                        "error": "rate_limited",
                        "retry_after_seconds": retry_after,
                        "message": "Too many requests.",
                    },
                    status=429,
                )

        # Parse query parameters
        since_str = request.query.get("since")
        until_str = request.query.get("until")
        since = _parse_iso_date(since_str)
        until = _parse_iso_date(until_str)

        # Get index
        index = await self.indexer.get_index()

        # Build project list with filtering
        projects_list = []
        total_sessions = 0

        for project in index.projects.values():
            # Count sessions with date filter
            session_count = 0
            total_size = 0
            latest_modified = None

            for session_id in project.session_ids:
                session = index.sessions.get(session_id)
                if session is None:
                    continue

                # Apply date filters
                if since and session.modified_at < since:
                    continue
                if until and session.modified_at > until:
                    continue

                session_count += 1
                total_size += session.size_bytes
                if latest_modified is None or session.modified_at > latest_modified:
                    latest_modified = session.modified_at

            if session_count > 0:
                from claude_session_player.watcher.indexer import decode_project_path

                projects_list.append({
                    "display_name": project.display_name,
                    "encoded_name": project.encoded_name,
                    "decoded_path": decode_project_path(project.encoded_name),
                    "session_count": session_count,
                    "latest_session_at": latest_modified.isoformat() if latest_modified else None,
                    "total_size_bytes": total_size,
                })
                total_sessions += session_count

        # Sort by latest session date (most recent first)
        projects_list.sort(
            key=lambda p: p["latest_session_at"] or "",
            reverse=True,
        )

        return web.json_response({
            "projects": projects_list,
            "total_projects": len(projects_list),
            "total_sessions": total_sessions,
            "index_age_seconds": self._get_index_age_seconds(),
        })

    async def handle_session_preview(self, request: web.Request) -> web.Response:
        """Handle GET /sessions/{session_id}/preview - get session preview.

        Query Parameters:
            limit: Number of events (max: 20, default: 5)

        Response 200:
            {
                "session_id": "930c1604-...",
                "project_name": "trello-clone",
                "summary": "Fix authentication bug",
                "total_events": 42,
                "preview_events": [...],
                "duration_ms": 1380000
            }

        Response 404: Session not found
        """
        session_id = request.match_info["session_id"]

        # Check if indexer is available
        if self.indexer is None:
            return web.json_response(
                {"error": "Search not available"},
                status=503,
            )

        # Check rate limit
        if self.preview_limiter:
            client_ip = self._get_client_ip(request)
            allowed, retry_after = self.preview_limiter.check(f"api:{client_ip}")
            if not allowed:
                return web.json_response(
                    {
                        "error": "rate_limited",
                        "retry_after_seconds": retry_after,
                        "message": "Too many requests.",
                    },
                    status=429,
                )

        # Parse limit
        limit_str = request.query.get("limit", "5")
        try:
            limit = int(limit_str)
            limit = max(1, min(20, limit))  # Clamp to 1-20
        except ValueError:
            limit = 5

        # Get session from index
        session = self.indexer.get_session(session_id)
        if session is None:
            return web.json_response(
                {
                    "error": "session_not_found",
                    "message": f"Session not found in index",
                },
                status=404,
            )

        # Read session file and generate preview events
        preview_events = []
        total_events = 0

        try:
            from claude_session_player.events import (
                AddBlock,
                BlockType,
                ProcessingContext,
                UserContent,
                AssistantContent,
                ToolCallContent,
            )
            from claude_session_player.watcher.transformer import transform

            # Read session file
            lines = []
            with open(session.file_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            # Process all lines to get events
            context = ProcessingContext()
            all_events, _ = transform(lines, context)

            # Filter to AddBlock events only (for counting and preview)
            add_events = [e for e in all_events if isinstance(e, AddBlock)]
            total_events = len(add_events)

            # Take last N events for preview
            preview_add_events = add_events[-limit:] if len(add_events) > limit else add_events

            # Convert to preview format
            for event in preview_add_events:
                block = event.block
                preview_event: dict = {
                    "type": block.type.value,
                    "timestamp": None,  # Not available from events
                }

                if isinstance(block.content, UserContent):
                    preview_event["text"] = block.content.text[:200]  # Truncate
                elif isinstance(block.content, AssistantContent):
                    preview_event["text"] = block.content.text[:200]  # Truncate
                elif isinstance(block.content, ToolCallContent):
                    preview_event["tool_name"] = block.content.tool_name
                    preview_event["label"] = block.content.label
                    if block.content.result:
                        # Truncate result preview
                        result = block.content.result
                        if len(result) > 50:
                            result = result[:50] + "..."
                        preview_event["result_preview"] = result

                preview_events.append(preview_event)

        except OSError:
            return web.json_response(
                {
                    "error": "session_not_found",
                    "message": "Session file not readable",
                },
                status=404,
            )

        return web.json_response({
            "session_id": session_id,
            "project_name": session.project_display_name,
            "summary": session.summary,
            "total_events": total_events,
            "preview_events": preview_events,
            "duration_ms": session.duration_ms,
        })

    async def handle_index_refresh(self, request: web.Request) -> web.Response:
        """Handle POST /index/refresh - force refresh the session index.

        Rate limit: Once per 60 seconds (global).

        Response 202:
            {
                "status": "started",
                "message": "Index refresh started",
                "estimated_duration_ms": 5000
            }

        Response 429: Rate limited
        """
        # Check if indexer is available
        if self.indexer is None:
            return web.json_response(
                {"error": "Search not available"},
                status=503,
            )

        # Check rate limit (global)
        if self.refresh_limiter:
            allowed, retry_after = self.refresh_limiter.check("global:refresh")
            if not allowed:
                return web.json_response(
                    {
                        "error": "rate_limited",
                        "retry_after_seconds": retry_after,
                    },
                    status=429,
                )

        # Trigger refresh in background
        asyncio.create_task(self._do_index_refresh())

        return web.json_response(
            {
                "status": "started",
                "message": "Index refresh started",
                "estimated_duration_ms": 5000,
            },
            status=202,
        )

    async def _do_index_refresh(self) -> None:
        """Perform index refresh in background."""
        if self.indexer is None:
            return
        try:
            await self.indexer.refresh(force=True)
        except Exception:
            # Log error but don't propagate
            pass

    async def handle_search_watch(self, request: web.Request) -> web.Response:
        """Handle POST /search/watch - attach session from search results.

        Request body:
            {
                "session_id": "930c1604-...",
                "destination": {
                    "type": "telegram",
                    "chat_id": "123456789"
                },
                "replay_count": 5
            }

        Response 201:
            {
                "attached": true,
                "session_id": "930c1604-...",
                "destination": {"type": "telegram", "chat_id": "123456789"},
                "replayed_events": 5,
                "session_summary": "Fix authentication bug"
            }

        Response 404: Session not found in index
        """
        # Check if indexer is available
        if self.indexer is None:
            return web.json_response(
                {"error": "Search not available"},
                status=503,
            )

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

        # Get session from index
        session = self.indexer.get_session(session_id)
        if session is None:
            return web.json_response(
                {
                    "error": "session_not_found",
                    "message": "Session not found in index",
                },
                status=404,
            )

        # Default replay_count to 5 for search/watch
        replay_count = data.get("replay_count", 5)

        # Create attach request with path from index
        attach_data = {
            "session_id": session_id,
            "path": str(session.file_path),
            "destination": destination,
            "replay_count": replay_count,
        }

        # Use existing attach handler
        # Create a mock request with the attach data
        class MockAttachRequest:
            async def json(self):
                return attach_data

        attach_response = await self.handle_attach(MockAttachRequest())

        # If attach succeeded, add session_summary to response
        if attach_response.status == 201:
            response_data = json.loads(attach_response.body)
            response_data["session_summary"] = session.summary
            return web.json_response(response_data, status=201)

        return attach_response

    def create_app(self) -> web.Application:
        """Create and configure the aiohttp web application.

        Returns:
            Configured aiohttp Application with all routes registered.
        """
        app = web.Application()

        # Core endpoints
        app.router.add_post("/attach", self.handle_attach)
        app.router.add_post("/detach", self.handle_detach)
        app.router.add_get("/sessions", self.handle_list_sessions)
        app.router.add_get("/sessions/{session_id}/events", self.handle_session_events)
        app.router.add_get("/health", self.handle_health)

        # Search endpoints
        app.router.add_get("/search", self.handle_search)
        app.router.add_get("/projects", self.handle_projects)
        app.router.add_get("/sessions/{session_id}/preview", self.handle_session_preview)
        app.router.add_post("/index/refresh", self.handle_index_refresh)
        app.router.add_post("/search/watch", self.handle_search_watch)

        return app
