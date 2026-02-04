"""Render cache for pre-rendered session screens.

This module provides a per-session cache that stores pre-rendered terminal-style
output for both desktop and mobile presets. The cache supports TTL-based eviction
and integrates with the ScreenRenderer for rendering.

Features:
- Pre-render desktop (40x80) and mobile (25x60) versions per session
- TTL-based eviction (30 minutes since last update)
- Background task for periodic eviction
- Thread-safe session management
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from ..events import Event
from .screen_renderer import Preset, ScreenRenderer

logger = logging.getLogger(__name__)

# Type alias for preset names
PresetName = Literal["desktop", "mobile"]

# Default TTL: 30 minutes in seconds
DEFAULT_TTL_SECONDS = 30 * 60

# Default eviction check interval: 5 minutes
DEFAULT_EVICTION_INTERVAL_SECONDS = 5 * 60


@dataclass
class CachedRender:
    """Holds pre-rendered content for both presets.

    Attributes:
        desktop: Pre-rendered desktop content (40x80 chars).
        mobile: Pre-rendered mobile content (25x60 chars).
        last_updated: Timestamp (monotonic) of last rebuild.
    """

    desktop: str
    mobile: str
    last_updated: float


@dataclass
class RenderCache:
    """Per-session render cache with TTL-based eviction.

    This cache stores pre-rendered terminal-style output for sessions,
    supporting both desktop and mobile presets. A background task
    periodically checks for and evicts stale entries.

    Attributes:
        ttl_seconds: Time-to-live in seconds (default: 1800 = 30 minutes).
        eviction_interval_seconds: Interval between eviction checks (default: 300 = 5 minutes).
    """

    ttl_seconds: float = DEFAULT_TTL_SECONDS
    eviction_interval_seconds: float = DEFAULT_EVICTION_INTERVAL_SECONDS

    _cache: dict[str, CachedRender] = field(default_factory=dict, repr=False)
    _renderer: ScreenRenderer = field(default_factory=ScreenRenderer, repr=False)
    _eviction_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _running: bool = field(default=False, repr=False)

    def rebuild(self, session_id: str, events: list[Event]) -> None:
        """Rebuild the cache for a session by pre-rendering both presets.

        This method renders the events to terminal-style text for both
        desktop (40x80) and mobile (25x60) presets and stores them in
        the cache with a fresh timestamp.

        Args:
            session_id: The session identifier.
            events: List of events to render.
        """
        desktop_content = self._renderer.render(events, preset=Preset.DESKTOP)
        mobile_content = self._renderer.render(events, preset=Preset.MOBILE)

        self._cache[session_id] = CachedRender(
            desktop=desktop_content,
            mobile=mobile_content,
            last_updated=time.monotonic(),
        )

        logger.debug(
            "Rebuilt render cache",
            extra={
                "session_id": session_id,
                "desktop_len": len(desktop_content),
                "mobile_len": len(mobile_content),
            },
        )

    def get(self, session_id: str, preset: PresetName) -> str | None:
        """Retrieve cached pre-rendered content for a session and preset.

        Args:
            session_id: The session identifier.
            preset: The preset to retrieve ("desktop" or "mobile").

        Returns:
            The pre-rendered content string, or None if not cached.
        """
        cached = self._cache.get(session_id)
        if cached is None:
            return None

        if preset == "desktop":
            return cached.desktop
        return cached.mobile

    def evict(self, session_id: str) -> None:
        """Remove a session from the cache.

        Does nothing if the session is not in the cache.

        Args:
            session_id: The session identifier to evict.
        """
        if session_id in self._cache:
            del self._cache[session_id]
            logger.debug("Evicted session from render cache", extra={"session_id": session_id})

    def get_last_updated(self, session_id: str) -> float | None:
        """Get the last update timestamp for a session.

        Args:
            session_id: The session identifier.

        Returns:
            Monotonic timestamp of last update, or None if not cached.
        """
        cached = self._cache.get(session_id)
        if cached is None:
            return None
        return cached.last_updated

    def contains(self, session_id: str) -> bool:
        """Check if a session is in the cache.

        Args:
            session_id: The session identifier.

        Returns:
            True if the session is cached, False otherwise.
        """
        return session_id in self._cache

    def session_count(self) -> int:
        """Return the number of sessions in the cache."""
        return len(self._cache)

    def clear(self) -> None:
        """Clear all entries from the cache."""
        count = len(self._cache)
        self._cache.clear()
        logger.debug("Cleared render cache", extra={"evicted_count": count})

    async def start(self) -> None:
        """Start the background eviction task.

        The eviction task periodically checks for and removes entries
        that have not been updated within the TTL period.
        """
        if self._running:
            logger.warning("RenderCache eviction task already running")
            return

        self._running = True
        self._eviction_task = asyncio.create_task(self._eviction_loop())
        logger.info(
            "Started render cache eviction task",
            extra={
                "ttl_seconds": self.ttl_seconds,
                "eviction_interval_seconds": self.eviction_interval_seconds,
            },
        )

    async def stop(self) -> None:
        """Stop the background eviction task.

        Cancels the eviction task and waits for it to complete.
        """
        if not self._running:
            return

        self._running = False

        if self._eviction_task is not None:
            self._eviction_task.cancel()
            try:
                await self._eviction_task
            except asyncio.CancelledError:
                pass
            self._eviction_task = None

        logger.info("Stopped render cache eviction task")

    async def _eviction_loop(self) -> None:
        """Background loop that periodically evicts stale entries."""
        while self._running:
            try:
                await asyncio.sleep(self.eviction_interval_seconds)
                self._evict_stale()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in render cache eviction loop")

    def _evict_stale(self) -> None:
        """Evict all entries that have exceeded the TTL.

        This method is called periodically by the eviction loop.
        """
        now = time.monotonic()
        cutoff = now - self.ttl_seconds

        stale_sessions = [
            session_id
            for session_id, cached in self._cache.items()
            if cached.last_updated < cutoff
        ]

        for session_id in stale_sessions:
            del self._cache[session_id]

        if stale_sessions:
            logger.info(
                "Evicted stale sessions from render cache",
                extra={
                    "evicted_count": len(stale_sessions),
                    "remaining_count": len(self._cache),
                },
            )

    def is_running(self) -> bool:
        """Check if the eviction task is running.

        Returns:
            True if the eviction task is running, False otherwise.
        """
        return self._running
