"""Tests for DestinationManager."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from claude_session_player.watcher.config import (
    ConfigManager,
    SessionConfig,
    SessionDestinations,
    SlackDestination,
    TelegramDestination,
)
from claude_session_player.watcher.destinations import (
    AttachedDestination,
    DestinationManager,
)


# ---------------------------------------------------------------------------
# AttachedDestination tests
# ---------------------------------------------------------------------------


class TestAttachedDestination:
    """Tests for AttachedDestination dataclass."""

    def test_create_telegram_destination(self) -> None:
        """Can create telegram AttachedDestination."""
        now = datetime.now()
        dest = AttachedDestination(
            type="telegram", identifier="123456789", attached_at=now
        )
        assert dest.type == "telegram"
        assert dest.identifier == "123456789"
        assert dest.attached_at == now

    def test_create_slack_destination(self) -> None:
        """Can create slack AttachedDestination."""
        now = datetime.now()
        dest = AttachedDestination(
            type="slack", identifier="C0123456789", attached_at=now
        )
        assert dest.type == "slack"
        assert dest.identifier == "C0123456789"
        assert dest.attached_at == now


# ---------------------------------------------------------------------------
# DestinationManager fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config_manager(tmp_path: Path) -> MagicMock:
    """Create a mock ConfigManager."""
    config = MagicMock(spec=ConfigManager)
    config.get.return_value = None
    config.load.return_value = []
    config.add_destination.return_value = True
    config.remove_destination.return_value = True
    return config


@pytest.fixture
def on_session_start() -> AsyncMock:
    """Create async mock for on_session_start callback."""
    return AsyncMock()


@pytest.fixture
def destination_manager(
    mock_config_manager: MagicMock,
    on_session_start: AsyncMock,
) -> DestinationManager:
    """Create a DestinationManager with mocks."""
    return DestinationManager(
        _config=mock_config_manager,
        _on_session_start=on_session_start,
    )


@pytest.fixture
def session_jsonl(tmp_path: Path) -> Path:
    """Create a temporary JSONL session file."""
    session_file = tmp_path / "session.jsonl"
    session_file.write_text('{"type": "user"}\n')
    return session_file


# ---------------------------------------------------------------------------
# Attach tests
# ---------------------------------------------------------------------------


class TestAttach:
    """Tests for DestinationManager.attach()."""

    @pytest.mark.asyncio
    async def test_first_attach_starts_session(
        self,
        destination_manager: DestinationManager,
        on_session_start: AsyncMock,
        session_jsonl: Path,
    ) -> None:
        """First attach to a session starts file watching."""
        result = await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier="123456789",
        )

        assert result is True
        on_session_start.assert_called_once_with("test-session", session_jsonl)

    @pytest.mark.asyncio
    async def test_subsequent_attach_does_not_start_session(
        self,
        destination_manager: DestinationManager,
        on_session_start: AsyncMock,
        session_jsonl: Path,
    ) -> None:
        """Subsequent attach does not start file watching again."""
        # First attach
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier="123456789",
        )

        # Second attach (different destination)
        result = await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="slack",
            identifier="C0123456789",
        )

        assert result is True
        # on_session_start should only be called once (for first attach)
        assert on_session_start.call_count == 1

    @pytest.mark.asyncio
    async def test_attach_is_idempotent(
        self,
        destination_manager: DestinationManager,
        on_session_start: AsyncMock,
        session_jsonl: Path,
    ) -> None:
        """Duplicate attach returns False without creating duplicate."""
        # First attach
        result1 = await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier="123456789",
        )

        # Duplicate attach
        result2 = await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier="123456789",
        )

        assert result1 is True
        assert result2 is False  # Idempotent - already attached

        # Should only have one destination
        destinations = destination_manager.get_destinations("test-session")
        assert len(destinations) == 1

    @pytest.mark.asyncio
    async def test_attach_without_path_uses_config(
        self,
        destination_manager: DestinationManager,
        mock_config_manager: MagicMock,
        on_session_start: AsyncMock,
        session_jsonl: Path,
    ) -> None:
        """Attach without path uses path from config."""
        # Setup config to return session
        mock_config_manager.get.return_value = SessionConfig(
            session_id="test-session",
            path=session_jsonl,
        )

        result = await destination_manager.attach(
            session_id="test-session",
            path=None,
            destination_type="telegram",
            identifier="123456789",
        )

        assert result is True
        on_session_start.assert_called_once_with("test-session", session_jsonl)

    @pytest.mark.asyncio
    async def test_attach_unknown_session_without_path_raises(
        self,
        destination_manager: DestinationManager,
        mock_config_manager: MagicMock,
    ) -> None:
        """Attach to unknown session without path raises ValueError."""
        mock_config_manager.get.return_value = None

        with pytest.raises(ValueError, match="unknown and no path provided"):
            await destination_manager.attach(
                session_id="unknown-session",
                path=None,
                destination_type="telegram",
                identifier="123456789",
            )

    @pytest.mark.asyncio
    async def test_attach_invalid_destination_type_raises(
        self,
        destination_manager: DestinationManager,
        session_jsonl: Path,
    ) -> None:
        """Attach with invalid destination_type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid destination_type"):
            await destination_manager.attach(
                session_id="test-session",
                path=session_jsonl,
                destination_type="invalid",
                identifier="123456789",
            )

    @pytest.mark.asyncio
    async def test_attach_persists_to_config(
        self,
        destination_manager: DestinationManager,
        mock_config_manager: MagicMock,
        session_jsonl: Path,
    ) -> None:
        """Attach persists destination to config."""
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier="123456789",
        )

        # Verify config was updated
        mock_config_manager.add_destination.assert_called_once()
        call_args = mock_config_manager.add_destination.call_args
        assert call_args[0][0] == "test-session"
        assert isinstance(call_args[0][1], TelegramDestination)
        assert call_args[0][1].chat_id == "123456789"

    @pytest.mark.asyncio
    async def test_attach_slack_destination(
        self,
        destination_manager: DestinationManager,
        mock_config_manager: MagicMock,
        session_jsonl: Path,
    ) -> None:
        """Attach slack destination persists correctly."""
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="slack",
            identifier="C0123456789",
        )

        call_args = mock_config_manager.add_destination.call_args
        assert isinstance(call_args[0][1], SlackDestination)
        assert call_args[0][1].channel == "C0123456789"


# ---------------------------------------------------------------------------
# Detach tests
# ---------------------------------------------------------------------------


class TestDetach:
    """Tests for DestinationManager.detach()."""

    @pytest.mark.asyncio
    async def test_detach_removes_destination(
        self,
        destination_manager: DestinationManager,
        session_jsonl: Path,
    ) -> None:
        """Detach removes destination from runtime state."""
        # First attach
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier="123456789",
        )

        # Detach
        result = await destination_manager.detach(
            session_id="test-session",
            destination_type="telegram",
            identifier="123456789",
        )

        assert result is True
        destinations = destination_manager.get_destinations("test-session")
        assert len(destinations) == 0

    @pytest.mark.asyncio
    async def test_detach_not_found_returns_false(
        self,
        destination_manager: DestinationManager,
    ) -> None:
        """Detach returns False if destination not found."""
        result = await destination_manager.detach(
            session_id="unknown-session",
            destination_type="telegram",
            identifier="123456789",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_detach_removes_from_config(
        self,
        destination_manager: DestinationManager,
        mock_config_manager: MagicMock,
        session_jsonl: Path,
    ) -> None:
        """Detach removes destination from config."""
        # First attach
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier="123456789",
        )

        # Detach
        await destination_manager.detach(
            session_id="test-session",
            destination_type="telegram",
            identifier="123456789",
        )

        mock_config_manager.remove_destination.assert_called_once()
        call_args = mock_config_manager.remove_destination.call_args
        assert call_args[0][0] == "test-session"
        assert isinstance(call_args[0][1], TelegramDestination)
        assert call_args[0][1].chat_id == "123456789"


# ---------------------------------------------------------------------------
# Restore from config tests
# ---------------------------------------------------------------------------


class TestRestoreFromConfig:
    """Tests for restore_from_config()."""

    @pytest.mark.asyncio
    async def test_restore_from_config_starts_sessions(
        self,
        mock_config_manager: MagicMock,
        on_session_start: AsyncMock,
        session_jsonl: Path,
    ) -> None:
        """restore_from_config starts file watching for sessions with destinations."""
        # Setup config to return sessions with destinations
        mock_config_manager.load.return_value = [
            SessionConfig(
                session_id="session-1",
                path=session_jsonl,
                destinations=SessionDestinations(
                    telegram=[TelegramDestination(chat_id="123456789")],
                    slack=[],
                ),
            ),
            SessionConfig(
                session_id="session-2",
                path=session_jsonl,
                destinations=SessionDestinations(
                    telegram=[],
                    slack=[SlackDestination(channel="C0123456789")],
                ),
            ),
        ]

        manager = DestinationManager(
            _config=mock_config_manager,
            _on_session_start=on_session_start,
        )

        await manager.restore_from_config()

        # Both sessions should have started
        assert on_session_start.call_count == 2

    @pytest.mark.asyncio
    async def test_restore_from_config_populates_runtime_state(
        self,
        mock_config_manager: MagicMock,
        on_session_start: AsyncMock,
        session_jsonl: Path,
    ) -> None:
        """restore_from_config populates runtime state."""
        mock_config_manager.load.return_value = [
            SessionConfig(
                session_id="session-1",
                path=session_jsonl,
                destinations=SessionDestinations(
                    telegram=[TelegramDestination(chat_id="123")],
                    slack=[SlackDestination(channel="C456")],
                ),
            ),
        ]

        manager = DestinationManager(
            _config=mock_config_manager,
            _on_session_start=on_session_start,
        )

        await manager.restore_from_config()

        destinations = manager.get_destinations("session-1")
        assert len(destinations) == 2
        assert any(d.type == "telegram" and d.identifier == "123" for d in destinations)
        assert any(d.type == "slack" and d.identifier == "C456" for d in destinations)

    @pytest.mark.asyncio
    async def test_restore_from_config_skips_empty_destinations(
        self,
        mock_config_manager: MagicMock,
        on_session_start: AsyncMock,
        session_jsonl: Path,
    ) -> None:
        """restore_from_config skips sessions with no destinations."""
        mock_config_manager.load.return_value = [
            SessionConfig(
                session_id="session-1",
                path=session_jsonl,
                destinations=SessionDestinations(telegram=[], slack=[]),
            ),
        ]

        manager = DestinationManager(
            _config=mock_config_manager,
            _on_session_start=on_session_start,
        )

        await manager.restore_from_config()

        # No sessions should have started (empty destinations)
        on_session_start.assert_not_called()


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------


class TestQueryMethods:
    """Tests for get_destinations and has_destinations."""

    @pytest.mark.asyncio
    async def test_get_destinations_empty(
        self,
        destination_manager: DestinationManager,
    ) -> None:
        """get_destinations returns empty list for unknown session."""
        destinations = destination_manager.get_destinations("unknown-session")
        assert destinations == []

    @pytest.mark.asyncio
    async def test_get_destinations_returns_copy(
        self,
        destination_manager: DestinationManager,
        session_jsonl: Path,
    ) -> None:
        """get_destinations returns a copy of the list."""
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier="123456789",
        )

        destinations1 = destination_manager.get_destinations("test-session")
        destinations2 = destination_manager.get_destinations("test-session")

        # Should be equal but not the same object
        assert destinations1 == destinations2
        assert destinations1 is not destinations2

    @pytest.mark.asyncio
    async def test_get_destinations_by_type(
        self,
        destination_manager: DestinationManager,
        session_jsonl: Path,
    ) -> None:
        """get_destinations_by_type filters by type."""
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier="123456789",
        )
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="slack",
            identifier="C0123456789",
        )

        telegram_dests = destination_manager.get_destinations_by_type(
            "test-session", "telegram"
        )
        slack_dests = destination_manager.get_destinations_by_type(
            "test-session", "slack"
        )

        assert len(telegram_dests) == 1
        assert telegram_dests[0].type == "telegram"
        assert len(slack_dests) == 1
        assert slack_dests[0].type == "slack"

    @pytest.mark.asyncio
    async def test_has_destinations_true(
        self,
        destination_manager: DestinationManager,
        session_jsonl: Path,
    ) -> None:
        """has_destinations returns True when destinations exist."""
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier="123456789",
        )

        assert destination_manager.has_destinations("test-session") is True

    @pytest.mark.asyncio
    async def test_has_destinations_false(
        self,
        destination_manager: DestinationManager,
    ) -> None:
        """has_destinations returns False when no destinations."""
        assert destination_manager.has_destinations("unknown-session") is False


# ---------------------------------------------------------------------------
# Module imports tests
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Tests for module imports and __all__."""

    def test_import_from_watcher(self) -> None:
        """Can import DestinationManager from watcher package."""
        from claude_session_player.watcher import DestinationManager as DM

        assert DM is DestinationManager

    def test_import_attached_destination_from_watcher(self) -> None:
        """Can import AttachedDestination from watcher package."""
        from claude_session_player.watcher import AttachedDestination as AD

        assert AD is AttachedDestination

    def test_in_all(self) -> None:
        """DestinationManager and AttachedDestination are in __all__."""
        from claude_session_player import watcher

        assert "DestinationManager" in watcher.__all__
        assert "AttachedDestination" in watcher.__all__
