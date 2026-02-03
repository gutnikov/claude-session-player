"""SSE (Server-Sent Events) endpoint for streaming session events.

This module provides SSE support for streaming session events to subscribers
with replay support via Last-Event-ID.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from claude_session_player.events import AddBlock, ClearAll, Event, UpdateBlock

if TYPE_CHECKING:
    from claude_session_player.watcher.event_buffer import EventBufferManager


class StreamResponse(Protocol):
    """Protocol for HTTP streaming response objects.

    Compatible with aiohttp.web.StreamResponse and similar.
    """

    async def prepare(self, request: object) -> None:
        """Prepare the response for streaming."""
        ...

    async def write(self, data: bytes) -> None:
        """Write data to the response stream."""
        ...

    async def write_eof(self) -> None:
        """Signal end of stream."""
        ...


# Keep-alive interval in seconds
KEEPALIVE_INTERVAL = 15


def _event_type_name(event: Event) -> str:
    """Map internal event type to SSE event type name.

    Args:
        event: The internal event.

    Returns:
        The SSE event type name (e.g., "add_block", "update_block", "clear_all").
    """
    if isinstance(event, AddBlock):
        return "add_block"
    elif isinstance(event, UpdateBlock):
        return "update_block"
    elif isinstance(event, ClearAll):
        return "clear_all"
    else:
        return "unknown"


def _event_to_data(event: Event) -> dict:
    """Convert an event to a JSON-serializable dict.

    Args:
        event: The internal event.

    Returns:
        Dictionary representation of the event for JSON serialization.
    """
    if isinstance(event, AddBlock):
        return {
            "block_id": event.block.id,
            "type": event.block.type.value,
            "content": event.block.content.to_dict(),
            "request_id": event.block.request_id,
        }
    elif isinstance(event, UpdateBlock):
        return {
            "block_id": event.block_id,
            "content": event.content.to_dict(),
        }
    elif isinstance(event, ClearAll):
        return {}
    else:
        return {}


def format_sse_message(
    event_id: str | None = None,
    event_type: str | None = None,
    data: dict | None = None,
) -> bytes:
    """Format a message as SSE.

    Args:
        event_id: The event ID (optional).
        event_type: The event type name (optional).
        data: The event data dictionary (optional).

    Returns:
        SSE-formatted message as bytes.
    """
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event_type is not None:
        lines.append(f"event: {event_type}")
    if data is not None:
        # JSON data on a single line
        lines.append(f"data: {json.dumps(data)}")
    lines.append("")  # Empty line terminates the message
    lines.append("")  # Extra newline for separation
    return "\n".join(lines).encode("utf-8")


def format_keepalive() -> bytes:
    """Format a keep-alive comment.

    Returns:
        SSE comment as bytes.
    """
    return b": keepalive\n\n"


@dataclass
class SSEConnection:
    """An individual SSE connection to a client.

    Manages sending events to a single SSE subscriber.
    """

    session_id: str
    response: StreamResponse
    _closed: bool = field(default=False, repr=False)

    async def send_event(
        self, event_id: str, event_type: str, data: dict
    ) -> None:
        """Send an event to the client.

        Args:
            event_id: The event ID.
            event_type: The event type name.
            data: The event data dictionary.

        Raises:
            ConnectionError: If the connection is closed or write fails.
        """
        if self._closed:
            raise ConnectionError("Connection is closed")

        message = format_sse_message(event_id=event_id, event_type=event_type, data=data)
        try:
            await self.response.write(message)
        except Exception as e:
            self._closed = True
            raise ConnectionError(f"Failed to write to response: {e}") from e

    async def send_keepalive(self) -> None:
        """Send a keep-alive comment to the client.

        Raises:
            ConnectionError: If the connection is closed or write fails.
        """
        if self._closed:
            raise ConnectionError("Connection is closed")

        try:
            await self.response.write(format_keepalive())
        except Exception as e:
            self._closed = True
            raise ConnectionError(f"Failed to write keepalive: {e}") from e

    async def close(self) -> None:
        """Close the connection."""
        if not self._closed:
            self._closed = True
            try:
                await self.response.write_eof()
            except Exception:
                pass  # Ignore errors during close

    @property
    def is_closed(self) -> bool:
        """Check if the connection is closed."""
        return self._closed


@dataclass
class SSEManager:
    """Manager for SSE connections.

    Handles connection lifecycle, event broadcasting, and keep-alive.
    """

    event_buffer: EventBufferManager
    _connections: dict[str, list[SSEConnection]] = field(
        default_factory=dict, repr=False
    )
    _keepalive_tasks: dict[int, asyncio.Task] = field(
        default_factory=dict, repr=False
    )  # keyed by id(connection)

    async def connect(
        self,
        session_id: str,
        response: StreamResponse,
        last_event_id: str | None = None,
    ) -> SSEConnection:
        """Create and register a new SSE connection.

        Replays buffered events if last_event_id is provided.

        Args:
            session_id: The session to subscribe to.
            response: The HTTP streaming response.
            last_event_id: The last event ID received (for replay).

        Returns:
            The new SSEConnection.
        """
        connection = SSEConnection(session_id=session_id, response=response)

        # Register the connection
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(connection)

        # Replay buffered events
        events_to_replay = self.event_buffer.get_events_since(session_id, last_event_id)
        for event_id, event in events_to_replay:
            event_type = _event_type_name(event)
            data = _event_to_data(event)
            try:
                await connection.send_event(event_id, event_type, data)
            except ConnectionError:
                # Client disconnected during replay
                await self.disconnect(connection)
                raise

        # Start keep-alive task
        task = asyncio.create_task(self._keepalive_loop(connection))
        self._keepalive_tasks[id(connection)] = task

        return connection

    async def disconnect(self, connection: SSEConnection) -> None:
        """Disconnect and clean up an SSE connection.

        Args:
            connection: The connection to disconnect.
        """
        conn_id = id(connection)

        # Cancel keep-alive task
        if conn_id in self._keepalive_tasks:
            task = self._keepalive_tasks.pop(conn_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Remove from connections
        session_id = connection.session_id
        if session_id in self._connections:
            try:
                self._connections[session_id].remove(connection)
            except ValueError:
                pass  # Already removed
            if not self._connections[session_id]:
                del self._connections[session_id]

        # Close the connection
        await connection.close()

    async def broadcast(
        self, session_id: str, event_id: str, event: Event
    ) -> None:
        """Broadcast an event to all subscribers of a session.

        Args:
            session_id: The session to broadcast to.
            event_id: The event ID.
            event: The event to broadcast.
        """
        if session_id not in self._connections:
            return

        event_type = _event_type_name(event)
        data = _event_to_data(event)

        # Copy the list to allow modification during iteration
        connections = list(self._connections.get(session_id, []))
        for connection in connections:
            try:
                await connection.send_event(event_id, event_type, data)
            except ConnectionError:
                # Client disconnected, clean up
                await self.disconnect(connection)

    async def close_session(self, session_id: str, reason: str) -> None:
        """Close all connections for a session and notify subscribers.

        Args:
            session_id: The session to close.
            reason: The reason for closing (e.g., "file_deleted", "unwatched").
        """
        if session_id not in self._connections:
            return

        # Send session_ended event to all subscribers
        data = {"reason": reason}

        # Copy the list to allow modification during iteration
        connections = list(self._connections.get(session_id, []))
        for connection in connections:
            try:
                # session_ended doesn't have an event_id from the buffer
                await connection.send_event(
                    event_id="session_ended",
                    event_type="session_ended",
                    data=data,
                )
            except ConnectionError:
                pass  # Ignore errors, we're closing anyway
            finally:
                await self.disconnect(connection)

    def get_connection_count(self, session_id: str) -> int:
        """Get the number of connections for a session.

        Args:
            session_id: The session ID.

        Returns:
            Number of active connections.
        """
        return len(self._connections.get(session_id, []))

    def get_total_connections(self) -> int:
        """Get the total number of active connections.

        Returns:
            Total number of connections across all sessions.
        """
        return sum(len(conns) for conns in self._connections.values())

    async def _keepalive_loop(self, connection: SSEConnection) -> None:
        """Send periodic keep-alive messages to a connection.

        Args:
            connection: The connection to keep alive.
        """
        while not connection.is_closed:
            try:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                if not connection.is_closed:
                    await connection.send_keepalive()
            except ConnectionError:
                # Connection closed, exit loop
                break
            except asyncio.CancelledError:
                # Task cancelled, exit loop
                break
