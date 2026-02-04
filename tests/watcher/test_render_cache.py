"""Tests for the render cache module."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    Event,
    UpdateBlock,
    UserContent,
)
from claude_session_player.watcher.render_cache import (
    CachedRender,
    RenderCache,
)


# --- Helper functions ---


def make_add_block_event(text: str = "test", block_id: str | None = None) -> AddBlock:
    """Create a simple AddBlock event for testing."""
    return AddBlock(
        block=Block(
            id=block_id or f"block_{text}",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text=text),
        )
    )


def make_user_event(text: str = "user input") -> AddBlock:
    """Create a user input AddBlock event for testing."""
    return AddBlock(
        block=Block(
            id=f"user_{text}",
            type=BlockType.USER,
            content=UserContent(text=text),
        )
    )


def make_events(count: int = 3) -> list[Event]:
    """Create a list of sample events for testing."""
    events: list[Event] = []
    events.append(make_user_event("Hello"))
    for i in range(count):
        events.append(make_add_block_event(f"response_{i}"))
    return events


# --- CachedRender tests ---


class TestCachedRender:
    """Tests for CachedRender dataclass."""

    def test_creation(self) -> None:
        """CachedRender stores all fields correctly."""
        cached = CachedRender(
            desktop="desktop content",
            mobile="mobile content",
            last_updated=123.456,
        )
        assert cached.desktop == "desktop content"
        assert cached.mobile == "mobile content"
        assert cached.last_updated == 123.456

    def test_immutable_fields(self) -> None:
        """CachedRender fields can be reassigned (mutable dataclass)."""
        cached = CachedRender(
            desktop="old",
            mobile="old",
            last_updated=100.0,
        )
        cached.desktop = "new"
        assert cached.desktop == "new"


# --- RenderCache creation tests ---


class TestRenderCacheCreation:
    """Tests for RenderCache creation and initialization."""

    def test_default_ttl(self) -> None:
        """RenderCache defaults to 30 minute TTL."""
        cache = RenderCache()
        assert cache.ttl_seconds == 30 * 60

    def test_custom_ttl(self) -> None:
        """RenderCache accepts custom TTL."""
        cache = RenderCache(ttl_seconds=60)
        assert cache.ttl_seconds == 60

    def test_default_eviction_interval(self) -> None:
        """RenderCache defaults to 5 minute eviction interval."""
        cache = RenderCache()
        assert cache.eviction_interval_seconds == 5 * 60

    def test_custom_eviction_interval(self) -> None:
        """RenderCache accepts custom eviction interval."""
        cache = RenderCache(eviction_interval_seconds=30)
        assert cache.eviction_interval_seconds == 30

    def test_empty_on_creation(self) -> None:
        """RenderCache is empty on creation."""
        cache = RenderCache()
        assert cache.session_count() == 0

    def test_not_running_on_creation(self) -> None:
        """RenderCache eviction task is not running on creation."""
        cache = RenderCache()
        assert not cache.is_running()


# --- RenderCache.rebuild() tests ---


class TestRenderCacheRebuild:
    """Tests for RenderCache.rebuild() method."""

    def test_rebuild_adds_session(self) -> None:
        """rebuild() adds a session to the cache."""
        cache = RenderCache()
        events = make_events()

        cache.rebuild("session_1", events)

        assert cache.contains("session_1")
        assert cache.session_count() == 1

    def test_rebuild_renders_both_presets(self) -> None:
        """rebuild() renders both desktop and mobile presets."""
        cache = RenderCache()
        events = make_events()

        cache.rebuild("session_1", events)

        desktop = cache.get("session_1", "desktop")
        mobile = cache.get("session_1", "mobile")

        assert desktop is not None
        assert mobile is not None
        assert desktop != mobile  # Different dimensions

    def test_rebuild_desktop_dimensions(self) -> None:
        """rebuild() renders desktop at 40x80 dimensions."""
        cache = RenderCache()
        events = make_events()

        cache.rebuild("session_1", events)
        desktop = cache.get("session_1", "desktop")

        assert desktop is not None
        lines = desktop.split("\n")
        # 40 total rows (38 content + 2 borders)
        assert len(lines) == 40
        # 80 cols width
        assert len(lines[0]) == 80

    def test_rebuild_mobile_dimensions(self) -> None:
        """rebuild() renders mobile at 25x60 dimensions."""
        cache = RenderCache()
        events = make_events()

        cache.rebuild("session_1", events)
        mobile = cache.get("session_1", "mobile")

        assert mobile is not None
        lines = mobile.split("\n")
        # 25 total rows (23 content + 2 borders)
        assert len(lines) == 25
        # 60 cols width
        assert len(lines[0]) == 60

    def test_rebuild_updates_existing(self) -> None:
        """rebuild() updates an existing session in the cache."""
        cache = RenderCache()

        events1 = [make_user_event("First")]
        cache.rebuild("session_1", events1)
        content1 = cache.get("session_1", "desktop")

        events2 = [make_user_event("Second")]
        cache.rebuild("session_1", events2)
        content2 = cache.get("session_1", "desktop")

        assert content1 != content2
        assert cache.session_count() == 1

    def test_rebuild_updates_timestamp(self) -> None:
        """rebuild() updates the last_updated timestamp."""
        cache = RenderCache()
        events = make_events()

        cache.rebuild("session_1", events)
        ts1 = cache.get_last_updated("session_1")

        time.sleep(0.01)  # Small delay to ensure different timestamp

        cache.rebuild("session_1", events)
        ts2 = cache.get_last_updated("session_1")

        assert ts1 is not None
        assert ts2 is not None
        assert ts2 > ts1

    def test_rebuild_empty_events(self) -> None:
        """rebuild() handles empty event list."""
        cache = RenderCache()

        cache.rebuild("session_1", [])

        assert cache.contains("session_1")
        desktop = cache.get("session_1", "desktop")
        assert desktop is not None
        # Should have empty framed content
        assert "─" in desktop  # Box drawing characters

    def test_rebuild_multiple_sessions(self) -> None:
        """rebuild() can handle multiple sessions."""
        cache = RenderCache()

        cache.rebuild("session_1", [make_user_event("One")])
        cache.rebuild("session_2", [make_user_event("Two")])
        cache.rebuild("session_3", [make_user_event("Three")])

        assert cache.session_count() == 3
        assert cache.contains("session_1")
        assert cache.contains("session_2")
        assert cache.contains("session_3")


# --- RenderCache.get() tests ---


class TestRenderCacheGet:
    """Tests for RenderCache.get() method."""

    def test_get_desktop(self) -> None:
        """get() returns desktop content."""
        cache = RenderCache()
        cache.rebuild("session_1", make_events())

        content = cache.get("session_1", "desktop")

        assert content is not None
        assert isinstance(content, str)

    def test_get_mobile(self) -> None:
        """get() returns mobile content."""
        cache = RenderCache()
        cache.rebuild("session_1", make_events())

        content = cache.get("session_1", "mobile")

        assert content is not None
        assert isinstance(content, str)

    def test_get_nonexistent_session(self) -> None:
        """get() returns None for nonexistent session."""
        cache = RenderCache()

        content = cache.get("nonexistent", "desktop")

        assert content is None

    def test_get_both_presets_different(self) -> None:
        """Desktop and mobile presets are different."""
        cache = RenderCache()
        cache.rebuild("session_1", make_events())

        desktop = cache.get("session_1", "desktop")
        mobile = cache.get("session_1", "mobile")

        assert desktop != mobile

    def test_get_preserves_content(self) -> None:
        """get() returns the same content on multiple calls."""
        cache = RenderCache()
        cache.rebuild("session_1", make_events())

        content1 = cache.get("session_1", "desktop")
        content2 = cache.get("session_1", "desktop")

        assert content1 == content2


# --- RenderCache.evict() tests ---


class TestRenderCacheEvict:
    """Tests for RenderCache.evict() method."""

    def test_evict_removes_session(self) -> None:
        """evict() removes session from cache."""
        cache = RenderCache()
        cache.rebuild("session_1", make_events())
        assert cache.contains("session_1")

        cache.evict("session_1")

        assert not cache.contains("session_1")
        assert cache.session_count() == 0

    def test_evict_nonexistent_is_noop(self) -> None:
        """evict() does nothing for nonexistent session."""
        cache = RenderCache()
        cache.rebuild("session_1", make_events())

        cache.evict("nonexistent")

        assert cache.contains("session_1")
        assert cache.session_count() == 1

    def test_evict_one_of_many(self) -> None:
        """evict() removes only the specified session."""
        cache = RenderCache()
        cache.rebuild("session_1", make_events())
        cache.rebuild("session_2", make_events())
        cache.rebuild("session_3", make_events())

        cache.evict("session_2")

        assert cache.contains("session_1")
        assert not cache.contains("session_2")
        assert cache.contains("session_3")
        assert cache.session_count() == 2


# --- RenderCache.get_last_updated() tests ---


class TestRenderCacheGetLastUpdated:
    """Tests for RenderCache.get_last_updated() method."""

    def test_returns_timestamp(self) -> None:
        """get_last_updated() returns monotonic timestamp."""
        cache = RenderCache()
        before = time.monotonic()

        cache.rebuild("session_1", make_events())

        ts = cache.get_last_updated("session_1")
        after = time.monotonic()

        assert ts is not None
        assert before <= ts <= after

    def test_returns_none_for_nonexistent(self) -> None:
        """get_last_updated() returns None for nonexistent session."""
        cache = RenderCache()

        ts = cache.get_last_updated("nonexistent")

        assert ts is None


# --- RenderCache.contains() tests ---


class TestRenderCacheContains:
    """Tests for RenderCache.contains() method."""

    def test_contains_cached_session(self) -> None:
        """contains() returns True for cached session."""
        cache = RenderCache()
        cache.rebuild("session_1", make_events())

        assert cache.contains("session_1")

    def test_not_contains_uncached(self) -> None:
        """contains() returns False for uncached session."""
        cache = RenderCache()

        assert not cache.contains("session_1")


# --- RenderCache.session_count() tests ---


class TestRenderCacheSessionCount:
    """Tests for RenderCache.session_count() method."""

    def test_count_empty(self) -> None:
        """session_count() returns 0 for empty cache."""
        cache = RenderCache()
        assert cache.session_count() == 0

    def test_count_increments(self) -> None:
        """session_count() increments with each session."""
        cache = RenderCache()

        cache.rebuild("session_1", make_events())
        assert cache.session_count() == 1

        cache.rebuild("session_2", make_events())
        assert cache.session_count() == 2

    def test_count_decrements_on_evict(self) -> None:
        """session_count() decrements on evict."""
        cache = RenderCache()
        cache.rebuild("session_1", make_events())
        cache.rebuild("session_2", make_events())

        cache.evict("session_1")

        assert cache.session_count() == 1


# --- RenderCache.clear() tests ---


class TestRenderCacheClear:
    """Tests for RenderCache.clear() method."""

    def test_clear_empties_cache(self) -> None:
        """clear() removes all sessions."""
        cache = RenderCache()
        cache.rebuild("session_1", make_events())
        cache.rebuild("session_2", make_events())
        cache.rebuild("session_3", make_events())

        cache.clear()

        assert cache.session_count() == 0
        assert not cache.contains("session_1")
        assert not cache.contains("session_2")
        assert not cache.contains("session_3")

    def test_clear_empty_cache(self) -> None:
        """clear() on empty cache is safe."""
        cache = RenderCache()

        cache.clear()

        assert cache.session_count() == 0


# --- RenderCache async lifecycle tests ---


class TestRenderCacheLifecycle:
    """Tests for RenderCache start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self) -> None:
        """start() sets running flag."""
        cache = RenderCache()

        await cache.start()

        try:
            assert cache.is_running()
        finally:
            await cache.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running(self) -> None:
        """stop() clears running flag."""
        cache = RenderCache()
        await cache.start()

        await cache.stop()

        assert not cache.is_running()

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self) -> None:
        """stop() without start() is safe."""
        cache = RenderCache()

        await cache.stop()

        assert not cache.is_running()

    @pytest.mark.asyncio
    async def test_double_start_warns(self) -> None:
        """Starting twice logs a warning."""
        cache = RenderCache()
        await cache.start()

        try:
            # Second start should be safe and log warning
            await cache.start()
            assert cache.is_running()
        finally:
            await cache.stop()

    @pytest.mark.asyncio
    async def test_double_stop_is_safe(self) -> None:
        """Stopping twice is safe."""
        cache = RenderCache()
        await cache.start()

        await cache.stop()
        await cache.stop()

        assert not cache.is_running()


# --- RenderCache TTL eviction tests ---


class TestRenderCacheTTLEviction:
    """Tests for TTL-based eviction."""

    def test_evict_stale_removes_old_entries(self) -> None:
        """_evict_stale() removes entries older than TTL."""
        cache = RenderCache(ttl_seconds=1.0)
        cache.rebuild("session_1", make_events())

        # Manually set timestamp to make entry stale
        cache._cache["session_1"] = CachedRender(
            desktop="old",
            mobile="old",
            last_updated=time.monotonic() - 2.0,  # 2 seconds ago (> 1s TTL)
        )

        cache._evict_stale()

        assert not cache.contains("session_1")

    def test_evict_stale_keeps_fresh_entries(self) -> None:
        """_evict_stale() keeps entries within TTL."""
        cache = RenderCache(ttl_seconds=60.0)
        cache.rebuild("session_1", make_events())

        cache._evict_stale()

        assert cache.contains("session_1")

    def test_evict_stale_partial(self) -> None:
        """_evict_stale() only removes stale entries."""
        cache = RenderCache(ttl_seconds=1.0)

        # Add fresh entry
        cache.rebuild("fresh", make_events())

        # Add stale entry
        cache.rebuild("stale", make_events())
        cache._cache["stale"] = CachedRender(
            desktop="old",
            mobile="old",
            last_updated=time.monotonic() - 2.0,
        )

        cache._evict_stale()

        assert cache.contains("fresh")
        assert not cache.contains("stale")

    @pytest.mark.asyncio
    async def test_eviction_loop_runs_periodically(self) -> None:
        """Eviction loop runs at configured interval."""
        cache = RenderCache(
            ttl_seconds=0.05,  # 50ms TTL
            eviction_interval_seconds=0.1,  # 100ms interval
        )

        # Add entry and make it stale
        cache.rebuild("session_1", make_events())
        cache._cache["session_1"] = CachedRender(
            desktop="old",
            mobile="old",
            last_updated=time.monotonic() - 1.0,  # Already stale
        )

        await cache.start()

        try:
            # Wait for eviction to run
            await asyncio.sleep(0.15)  # 150ms should be enough for one cycle

            assert not cache.contains("session_1")
        finally:
            await cache.stop()


# --- RenderCache content rendering tests ---


class TestRenderCacheContent:
    """Tests for content rendering correctness."""

    def test_renders_user_content(self) -> None:
        """Cache renders user input with > prefix."""
        cache = RenderCache()
        events = [make_user_event("Hello Claude")]

        cache.rebuild("session_1", events)
        content = cache.get("session_1", "desktop")

        assert content is not None
        assert "> Hello Claude" in content

    def test_renders_assistant_content(self) -> None:
        """Cache renders assistant response with * prefix."""
        cache = RenderCache()
        events = [make_add_block_event("Hello user")]

        cache.rebuild("session_1", events)
        content = cache.get("session_1", "desktop")

        assert content is not None
        assert "* Hello user" in content

    def test_renders_clear_all(self) -> None:
        """Cache handles ClearAll events."""
        cache = RenderCache()
        events: list[Event] = [
            make_user_event("Before clear"),
            ClearAll(),
            make_user_event("After clear"),
        ]

        cache.rebuild("session_1", events)
        content = cache.get("session_1", "desktop")

        assert content is not None
        # Only "After clear" should be visible
        assert "After clear" in content
        assert "Before clear" not in content

    def test_renders_update_block(self) -> None:
        """Cache handles UpdateBlock events."""
        cache = RenderCache()
        events: list[Event] = [
            make_add_block_event("initial", block_id="block_1"),
            UpdateBlock(
                block_id="block_1",
                content=AssistantContent(text="updated"),
            ),
        ]

        cache.rebuild("session_1", events)
        content = cache.get("session_1", "desktop")

        assert content is not None
        # Updated text should be visible
        assert "updated" in content
        # Initial text should be replaced
        assert "initial" not in content


# --- RenderCache integration tests ---


class TestRenderCacheIntegration:
    """Integration tests for RenderCache."""

    @pytest.mark.asyncio
    async def test_full_workflow(self) -> None:
        """Test complete workflow: start, rebuild, get, evict, stop."""
        cache = RenderCache(
            ttl_seconds=60,
            eviction_interval_seconds=30,
        )

        await cache.start()

        try:
            # Add sessions
            cache.rebuild("session_1", [make_user_event("Session 1")])
            cache.rebuild("session_2", [make_user_event("Session 2")])

            # Verify content
            assert cache.session_count() == 2
            assert "Session 1" in (cache.get("session_1", "desktop") or "")
            assert "Session 2" in (cache.get("session_2", "mobile") or "")

            # Evict one session
            cache.evict("session_1")
            assert cache.session_count() == 1
            assert not cache.contains("session_1")

            # Update remaining session
            cache.rebuild("session_2", [make_user_event("Updated Session 2")])
            content = cache.get("session_2", "desktop")
            assert content is not None
            assert "Updated Session 2" in content

        finally:
            await cache.stop()

        assert not cache.is_running()

    def test_concurrent_access(self) -> None:
        """Test concurrent rebuilds (sync operations are safe)."""
        cache = RenderCache()

        # Simulate concurrent access
        for i in range(100):
            session_id = f"session_{i % 10}"
            cache.rebuild(session_id, [make_user_event(f"Message {i}")])

        # All 10 unique sessions should exist
        assert cache.session_count() == 10

    def test_large_event_list(self) -> None:
        """Test handling large event lists."""
        cache = RenderCache()

        # Create many events
        events: list[Event] = []
        events.append(make_user_event("Start"))
        for i in range(1000):
            events.append(make_add_block_event(f"Response {i}"))

        cache.rebuild("session_1", events)

        # Should render without error
        desktop = cache.get("session_1", "desktop")
        mobile = cache.get("session_1", "mobile")

        assert desktop is not None
        assert mobile is not None
        # Viewport shows only recent content
        assert len(desktop.split("\n")) == 40  # 40 total (38 content + 2 borders)
        assert len(mobile.split("\n")) == 25  # 25 total (23 content + 2 borders)
