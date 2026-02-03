"""Tests for ConfigManager and SessionConfig."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from claude_session_player.watcher.config import (
    BotConfig,
    ConfigManager,
    SessionConfig,
    SessionDestinations,
    SlackDestination,
    TelegramDestination,
)


# ---------------------------------------------------------------------------
# TelegramDestination tests
# ---------------------------------------------------------------------------


class TestTelegramDestination:
    """Tests for TelegramDestination dataclass."""

    def test_create_telegram_destination(self) -> None:
        """Can create TelegramDestination with chat_id."""
        dest = TelegramDestination(chat_id="123456789")
        assert dest.chat_id == "123456789"

    def test_to_dict(self) -> None:
        """to_dict returns expected structure."""
        dest = TelegramDestination(chat_id="123456789")
        result = dest.to_dict()
        assert result == {"chat_id": "123456789"}

    def test_from_dict(self) -> None:
        """from_dict reconstructs TelegramDestination correctly."""
        data = {"chat_id": "123456789"}
        dest = TelegramDestination.from_dict(data)
        assert dest.chat_id == "123456789"

    def test_roundtrip(self) -> None:
        """to_dict/from_dict round-trip preserves data."""
        original = TelegramDestination(chat_id="-100987654321")
        restored = TelegramDestination.from_dict(original.to_dict())
        assert restored.chat_id == original.chat_id


# ---------------------------------------------------------------------------
# SlackDestination tests
# ---------------------------------------------------------------------------


class TestSlackDestination:
    """Tests for SlackDestination dataclass."""

    def test_create_slack_destination(self) -> None:
        """Can create SlackDestination with channel."""
        dest = SlackDestination(channel="C0123456789")
        assert dest.channel == "C0123456789"

    def test_to_dict(self) -> None:
        """to_dict returns expected structure."""
        dest = SlackDestination(channel="C0123456789")
        result = dest.to_dict()
        assert result == {"channel": "C0123456789"}

    def test_from_dict(self) -> None:
        """from_dict reconstructs SlackDestination correctly."""
        data = {"channel": "C0123456789"}
        dest = SlackDestination.from_dict(data)
        assert dest.channel == "C0123456789"

    def test_roundtrip(self) -> None:
        """to_dict/from_dict round-trip preserves data."""
        original = SlackDestination(channel="general")
        restored = SlackDestination.from_dict(original.to_dict())
        assert restored.channel == original.channel


# ---------------------------------------------------------------------------
# SessionDestinations tests
# ---------------------------------------------------------------------------


class TestSessionDestinations:
    """Tests for SessionDestinations dataclass."""

    def test_create_empty_destinations(self) -> None:
        """Default destinations are empty lists."""
        dest = SessionDestinations()
        assert dest.telegram == []
        assert dest.slack == []

    def test_create_with_destinations(self) -> None:
        """Can create with telegram and slack destinations."""
        telegram = [TelegramDestination(chat_id="123")]
        slack = [SlackDestination(channel="C123")]
        dest = SessionDestinations(telegram=telegram, slack=slack)
        assert len(dest.telegram) == 1
        assert len(dest.slack) == 1
        assert dest.telegram[0].chat_id == "123"
        assert dest.slack[0].channel == "C123"

    def test_to_dict(self) -> None:
        """to_dict returns expected structure."""
        dest = SessionDestinations(
            telegram=[TelegramDestination(chat_id="123")],
            slack=[SlackDestination(channel="C123")],
        )
        result = dest.to_dict()
        assert result == {
            "telegram": [{"chat_id": "123"}],
            "slack": [{"channel": "C123"}],
        }

    def test_from_dict(self) -> None:
        """from_dict reconstructs SessionDestinations correctly."""
        data = {
            "telegram": [{"chat_id": "123"}, {"chat_id": "456"}],
            "slack": [{"channel": "C123"}],
        }
        dest = SessionDestinations.from_dict(data)
        assert len(dest.telegram) == 2
        assert len(dest.slack) == 1
        assert dest.telegram[0].chat_id == "123"
        assert dest.telegram[1].chat_id == "456"
        assert dest.slack[0].channel == "C123"

    def test_from_dict_empty(self) -> None:
        """from_dict handles empty/missing keys."""
        dest = SessionDestinations.from_dict({})
        assert dest.telegram == []
        assert dest.slack == []

    def test_roundtrip(self) -> None:
        """to_dict/from_dict round-trip preserves data."""
        original = SessionDestinations(
            telegram=[TelegramDestination(chat_id="123")],
            slack=[SlackDestination(channel="C123"), SlackDestination(channel="C456")],
        )
        restored = SessionDestinations.from_dict(original.to_dict())
        assert len(restored.telegram) == len(original.telegram)
        assert len(restored.slack) == len(original.slack)


# ---------------------------------------------------------------------------
# BotConfig tests
# ---------------------------------------------------------------------------


class TestBotConfig:
    """Tests for BotConfig dataclass."""

    def test_create_empty_bot_config(self) -> None:
        """Default bot config has no tokens."""
        config = BotConfig()
        assert config.telegram_token is None
        assert config.slack_token is None

    def test_create_with_tokens(self) -> None:
        """Can create with telegram and slack tokens."""
        config = BotConfig(
            telegram_token="BOT_TOKEN",
            slack_token="xoxb-token",
        )
        assert config.telegram_token == "BOT_TOKEN"
        assert config.slack_token == "xoxb-token"

    def test_to_dict_with_tokens(self) -> None:
        """to_dict includes configured tokens."""
        config = BotConfig(
            telegram_token="BOT_TOKEN",
            slack_token="xoxb-token",
        )
        result = config.to_dict()
        assert result == {
            "telegram": {"token": "BOT_TOKEN"},
            "slack": {"token": "xoxb-token"},
        }

    def test_to_dict_empty(self) -> None:
        """to_dict returns empty dict when no tokens."""
        config = BotConfig()
        result = config.to_dict()
        assert result == {}

    def test_to_dict_partial(self) -> None:
        """to_dict only includes configured tokens."""
        config = BotConfig(telegram_token="BOT_TOKEN")
        result = config.to_dict()
        assert result == {"telegram": {"token": "BOT_TOKEN"}}

    def test_from_dict_with_tokens(self) -> None:
        """from_dict reconstructs BotConfig correctly."""
        data = {
            "telegram": {"token": "BOT_TOKEN"},
            "slack": {"token": "xoxb-token"},
        }
        config = BotConfig.from_dict(data)
        assert config.telegram_token == "BOT_TOKEN"
        assert config.slack_token == "xoxb-token"

    def test_from_dict_empty(self) -> None:
        """from_dict handles empty dict."""
        config = BotConfig.from_dict({})
        assert config.telegram_token is None
        assert config.slack_token is None

    def test_from_dict_partial(self) -> None:
        """from_dict handles partial config."""
        config = BotConfig.from_dict({"slack": {"token": "xoxb-token"}})
        assert config.telegram_token is None
        assert config.slack_token == "xoxb-token"

    def test_roundtrip(self) -> None:
        """to_dict/from_dict round-trip preserves data."""
        original = BotConfig(
            telegram_token="BOT_TOKEN",
            slack_token="xoxb-token",
        )
        restored = BotConfig.from_dict(original.to_dict())
        assert restored.telegram_token == original.telegram_token
        assert restored.slack_token == original.slack_token


# ---------------------------------------------------------------------------
# SessionConfig tests
# ---------------------------------------------------------------------------


class TestSessionConfig:
    """Tests for SessionConfig dataclass."""

    def test_create_session_config(self) -> None:
        """Can create SessionConfig with required fields."""
        config = SessionConfig(
            session_id="test-session-001",
            path=Path("/path/to/session.jsonl"),
        )
        assert config.session_id == "test-session-001"
        assert config.path == Path("/path/to/session.jsonl")

    def test_create_with_empty_destinations_by_default(self) -> None:
        """SessionConfig has empty destinations by default."""
        config = SessionConfig(
            session_id="test-session-001",
            path=Path("/path/to/session.jsonl"),
        )
        assert config.destinations.telegram == []
        assert config.destinations.slack == []

    def test_create_with_destinations(self) -> None:
        """Can create SessionConfig with destinations."""
        destinations = SessionDestinations(
            telegram=[TelegramDestination(chat_id="123")],
            slack=[SlackDestination(channel="C123")],
        )
        config = SessionConfig(
            session_id="test-session-001",
            path=Path("/path/to/session.jsonl"),
            destinations=destinations,
        )
        assert len(config.destinations.telegram) == 1
        assert len(config.destinations.slack) == 1

    def test_to_dict(self) -> None:
        """to_dict returns expected structure (old format)."""
        config = SessionConfig(
            session_id="test-session-001",
            path=Path("/path/to/session.jsonl"),
        )
        result = config.to_dict()
        assert result == {
            "id": "test-session-001",
            "path": "/path/to/session.jsonl",
        }

    def test_to_new_dict(self) -> None:
        """to_new_dict returns new format structure."""
        destinations = SessionDestinations(
            telegram=[TelegramDestination(chat_id="123")],
            slack=[SlackDestination(channel="C123")],
        )
        config = SessionConfig(
            session_id="test-session-001",
            path=Path("/path/to/session.jsonl"),
            destinations=destinations,
        )
        result = config.to_new_dict()
        assert result == {
            "path": "/path/to/session.jsonl",
            "destinations": {
                "telegram": [{"chat_id": "123"}],
                "slack": [{"channel": "C123"}],
            },
        }

    def test_from_dict(self) -> None:
        """from_dict reconstructs SessionConfig from old format."""
        data = {
            "id": "test-session-001",
            "path": "/path/to/session.jsonl",
        }
        config = SessionConfig.from_dict(data)
        assert config.session_id == "test-session-001"
        assert config.path == Path("/path/to/session.jsonl")
        assert config.destinations.telegram == []
        assert config.destinations.slack == []

    def test_from_new_dict(self) -> None:
        """from_new_dict reconstructs SessionConfig from new format."""
        data = {
            "path": "/path/to/session.jsonl",
            "destinations": {
                "telegram": [{"chat_id": "123"}],
                "slack": [{"channel": "C123"}],
            },
        }
        config = SessionConfig.from_new_dict("test-session-001", data)
        assert config.session_id == "test-session-001"
        assert config.path == Path("/path/to/session.jsonl")
        assert len(config.destinations.telegram) == 1
        assert len(config.destinations.slack) == 1

    def test_from_new_dict_no_destinations(self) -> None:
        """from_new_dict handles missing destinations."""
        data = {"path": "/path/to/session.jsonl"}
        config = SessionConfig.from_new_dict("test-session-001", data)
        assert config.destinations.telegram == []
        assert config.destinations.slack == []

    def test_roundtrip(self) -> None:
        """to_dict/from_dict round-trip preserves data."""
        original = SessionConfig(
            session_id="test-session-001",
            path=Path("/path/to/session.jsonl"),
        )
        restored = SessionConfig.from_dict(original.to_dict())
        assert restored.session_id == original.session_id
        assert restored.path == original.path


# ---------------------------------------------------------------------------
# ConfigManager fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_config_path(tmp_path: Path) -> Path:
    """Return path to config.yaml in temp directory."""
    return tmp_path / "config.yaml"


@pytest.fixture
def config_manager(tmp_config_path: Path) -> ConfigManager:
    """Create ConfigManager with temp config path."""
    return ConfigManager(tmp_config_path)


@pytest.fixture
def sample_session_file(tmp_path: Path) -> Path:
    """Create a sample session file and return its path."""
    session_file = tmp_path / "session.jsonl"
    session_file.write_text('{"type": "user"}\n')
    return session_file


@pytest.fixture
def another_session_file(tmp_path: Path) -> Path:
    """Create another sample session file and return its path."""
    session_file = tmp_path / "another-session.jsonl"
    session_file.write_text('{"type": "user"}\n')
    return session_file


# ---------------------------------------------------------------------------
# ConfigManager.load tests
# ---------------------------------------------------------------------------


class TestConfigManagerLoad:
    """Tests for ConfigManager.load()."""

    def test_load_missing_config_returns_empty_list(
        self, config_manager: ConfigManager
    ) -> None:
        """load() returns empty list when config file doesn't exist."""
        sessions = config_manager.load()
        assert sessions == []

    def test_load_empty_config_returns_empty_list(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """load() returns empty list when config file is empty."""
        tmp_config_path.write_text("")
        sessions = config_manager.load()
        assert sessions == []

    def test_load_config_without_sessions_key(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """load() returns empty list when 'sessions' key is missing."""
        tmp_config_path.write_text("other_key: value\n")
        sessions = config_manager.load()
        assert sessions == []

    def test_load_returns_sessions(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """load() returns list of SessionConfig from YAML file."""
        yaml_content = """sessions:
  - id: "session-001"
    path: "/path/to/first.jsonl"
  - id: "session-002"
    path: "/path/to/second.jsonl"
"""
        tmp_config_path.write_text(yaml_content)
        sessions = config_manager.load()

        assert len(sessions) == 2
        assert sessions[0].session_id == "session-001"
        assert sessions[0].path == Path("/path/to/first.jsonl")
        assert sessions[1].session_id == "session-002"
        assert sessions[1].path == Path("/path/to/second.jsonl")


# ---------------------------------------------------------------------------
# ConfigManager.save tests
# ---------------------------------------------------------------------------


class TestConfigManagerSave:
    """Tests for ConfigManager.save()."""

    def test_save_creates_config_file(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """save() creates config file if it doesn't exist."""
        sessions = [
            SessionConfig(
                session_id="test-001", path=Path("/path/to/session.jsonl")
            )
        ]
        config_manager.save(sessions)

        assert tmp_config_path.exists()
        content = tmp_config_path.read_text()
        assert "test-001" in content
        assert "/path/to/session.jsonl" in content

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        """save() creates parent directories if they don't exist."""
        nested_path = tmp_path / "nested" / "dir" / "config.yaml"
        manager = ConfigManager(nested_path)

        sessions = [
            SessionConfig(
                session_id="test-001", path=Path("/path/to/session.jsonl")
            )
        ]
        manager.save(sessions)

        assert nested_path.exists()

    def test_save_overwrites_existing_config(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """save() overwrites existing config file."""
        tmp_config_path.write_text("old content\n")

        sessions = [
            SessionConfig(
                session_id="new-session", path=Path("/path/to/new.jsonl")
            )
        ]
        config_manager.save(sessions)

        content = tmp_config_path.read_text()
        assert "old content" not in content
        assert "new-session" in content

    def test_save_empty_list(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """save() with empty list creates valid YAML with empty sessions."""
        config_manager.save([])

        assert tmp_config_path.exists()
        sessions = config_manager.load()
        assert sessions == []


# ---------------------------------------------------------------------------
# ConfigManager.add tests
# ---------------------------------------------------------------------------


class TestConfigManagerAdd:
    """Tests for ConfigManager.add()."""

    def test_add_creates_entry_in_config(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """add() creates a new entry in the config file."""
        config_manager.add("session-001", sample_session_file)

        sessions = config_manager.load()
        assert len(sessions) == 1
        assert sessions[0].session_id == "session-001"
        assert sessions[0].path == sample_session_file

    def test_add_multiple_sessions(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        another_session_file: Path,
    ) -> None:
        """add() can add multiple sessions."""
        config_manager.add("session-001", sample_session_file)
        config_manager.add("session-002", another_session_file)

        sessions = config_manager.load()
        assert len(sessions) == 2
        session_ids = {s.session_id for s in sessions}
        assert session_ids == {"session-001", "session-002"}

    def test_add_rejects_duplicate_session_id(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        another_session_file: Path,
    ) -> None:
        """add() raises ValueError for duplicate session_id."""
        config_manager.add("session-001", sample_session_file)

        with pytest.raises(ValueError, match="Session already exists"):
            config_manager.add("session-001", another_session_file)

    def test_add_rejects_non_absolute_path(
        self,
        config_manager: ConfigManager,
    ) -> None:
        """add() raises ValueError for non-absolute path."""
        with pytest.raises(ValueError, match="Path must be absolute"):
            config_manager.add("session-001", Path("relative/path.jsonl"))

    def test_add_rejects_non_existent_file(
        self,
        config_manager: ConfigManager,
        tmp_path: Path,
    ) -> None:
        """add() raises FileNotFoundError for non-existent file."""
        non_existent = tmp_path / "does-not-exist.jsonl"

        with pytest.raises(FileNotFoundError, match="Session file not found"):
            config_manager.add("session-001", non_existent)


# ---------------------------------------------------------------------------
# ConfigManager.remove tests
# ---------------------------------------------------------------------------


class TestConfigManagerRemove:
    """Tests for ConfigManager.remove()."""

    def test_remove_deletes_entry(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """remove() deletes the session from config."""
        config_manager.add("session-001", sample_session_file)
        config_manager.remove("session-001")

        sessions = config_manager.load()
        assert len(sessions) == 0

    def test_remove_only_removes_specified_session(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        another_session_file: Path,
    ) -> None:
        """remove() only removes the specified session, not others."""
        config_manager.add("session-001", sample_session_file)
        config_manager.add("session-002", another_session_file)

        config_manager.remove("session-001")

        sessions = config_manager.load()
        assert len(sessions) == 1
        assert sessions[0].session_id == "session-002"

    def test_remove_nonexistent_raises_keyerror(
        self,
        config_manager: ConfigManager,
    ) -> None:
        """remove() raises KeyError for non-existent session."""
        with pytest.raises(KeyError, match="Session not found"):
            config_manager.remove("nonexistent-session")


# ---------------------------------------------------------------------------
# ConfigManager.get tests
# ---------------------------------------------------------------------------


class TestConfigManagerGet:
    """Tests for ConfigManager.get()."""

    def test_get_returns_session(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """get() returns SessionConfig for existing session."""
        config_manager.add("session-001", sample_session_file)

        result = config_manager.get("session-001")

        assert result is not None
        assert result.session_id == "session-001"
        assert result.path == sample_session_file

    def test_get_returns_none_for_nonexistent(
        self,
        config_manager: ConfigManager,
    ) -> None:
        """get() returns None for non-existent session."""
        result = config_manager.get("nonexistent-session")
        assert result is None

    def test_get_with_multiple_sessions(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        another_session_file: Path,
    ) -> None:
        """get() returns correct session when multiple exist."""
        config_manager.add("session-001", sample_session_file)
        config_manager.add("session-002", another_session_file)

        result = config_manager.get("session-002")

        assert result is not None
        assert result.session_id == "session-002"
        assert result.path == another_session_file


# ---------------------------------------------------------------------------
# ConfigManager.list_all tests
# ---------------------------------------------------------------------------


class TestConfigManagerListAll:
    """Tests for ConfigManager.list_all()."""

    def test_list_all_returns_empty_for_no_sessions(
        self,
        config_manager: ConfigManager,
    ) -> None:
        """list_all() returns empty list when no sessions configured."""
        result = config_manager.list_all()
        assert result == []

    def test_list_all_returns_all_sessions(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        another_session_file: Path,
    ) -> None:
        """list_all() returns all configured sessions."""
        config_manager.add("session-001", sample_session_file)
        config_manager.add("session-002", another_session_file)

        result = config_manager.list_all()

        assert len(result) == 2
        session_ids = {s.session_id for s in result}
        assert session_ids == {"session-001", "session-002"}


# ---------------------------------------------------------------------------
# Load/save round-trip tests
# ---------------------------------------------------------------------------


class TestLoadSaveRoundTrip:
    """Tests for load/save round-trip."""

    def test_roundtrip_preserves_data(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        another_session_file: Path,
    ) -> None:
        """load/save round-trip preserves all session data."""
        original_sessions = [
            SessionConfig(session_id="session-001", path=sample_session_file),
            SessionConfig(session_id="session-002", path=another_session_file),
        ]

        config_manager.save(original_sessions)
        loaded_sessions = config_manager.load()

        assert len(loaded_sessions) == len(original_sessions)
        for original, loaded in zip(original_sessions, loaded_sessions):
            assert loaded.session_id == original.session_id
            assert loaded.path == original.path

    def test_roundtrip_with_special_characters_in_path(
        self,
        config_manager: ConfigManager,
        tmp_path: Path,
    ) -> None:
        """load/save round-trip handles special characters in path."""
        # Create session file with spaces and special chars
        session_file = tmp_path / "session with spaces & special.jsonl"
        session_file.write_text('{"type": "user"}\n')

        config_manager.add("session-special", session_file)
        loaded = config_manager.get("session-special")

        assert loaded is not None
        assert loaded.path == session_file


# ---------------------------------------------------------------------------
# Atomic write tests
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    """Tests for atomic write functionality."""

    def test_no_temp_files_left_on_success(
        self,
        config_manager: ConfigManager,
        tmp_config_path: Path,
    ) -> None:
        """No temp files remain after successful save."""
        sessions = [
            SessionConfig(
                session_id="test-001", path=Path("/path/to/session.jsonl")
            )
        ]
        config_manager.save(sessions)

        # Check for any temp files in the directory
        temp_files = list(tmp_config_path.parent.glob(".config_*.yaml.tmp"))
        assert len(temp_files) == 0

    def test_atomic_write_temp_file_cleaned_on_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Temp files are cleaned up if write fails mid-operation."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path)

        # Track temp file path
        temp_file_path: str | None = None
        original_fdopen = os.fdopen

        def track_fdopen(fd: int, mode: str, **kwargs):
            nonlocal temp_file_path
            # Get the path from /proc/self/fd on Linux or just track that we created one
            f = original_fdopen(fd, mode, **kwargs)
            # Simulate an error after writing begins
            raise IOError("Simulated write failure")

        monkeypatch.setattr(os, "fdopen", track_fdopen)

        sessions = [
            SessionConfig(
                session_id="test-001", path=Path("/path/to/session.jsonl")
            )
        ]

        with pytest.raises(IOError, match="Simulated write failure"):
            manager.save(sessions)

        # Check no temp files left behind
        temp_files = list(config_path.parent.glob(".config_*.yaml.tmp"))
        assert len(temp_files) == 0

    def test_config_path_property(
        self,
        tmp_config_path: Path,
    ) -> None:
        """config_path property returns the configuration file path."""
        manager = ConfigManager(tmp_config_path)
        assert manager.config_path == tmp_config_path


# ---------------------------------------------------------------------------
# ConfigManager old format migration tests
# ---------------------------------------------------------------------------


class TestConfigManagerOldFormat:
    """Tests for loading and migrating old config format."""

    def test_load_old_format_config(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """load() correctly parses old format config."""
        yaml_content = """sessions:
  - id: "session-001"
    path: "/path/to/first.jsonl"
  - id: "session-002"
    path: "/path/to/second.jsonl"
"""
        tmp_config_path.write_text(yaml_content)
        sessions = config_manager.load()

        assert len(sessions) == 2
        assert sessions[0].session_id == "session-001"
        assert sessions[0].path == Path("/path/to/first.jsonl")
        # Old format should result in empty destinations
        assert sessions[0].destinations.telegram == []
        assert sessions[0].destinations.slack == []

    def test_load_new_format_config(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """load() correctly parses new format config."""
        yaml_content = """bots:
  telegram:
    token: "BOT_TOKEN"
  slack:
    token: "xoxb-token"
sessions:
  session-001:
    path: "/path/to/first.jsonl"
    destinations:
      telegram:
        - chat_id: "123456789"
      slack:
        - channel: "C0123456789"
  session-002:
    path: "/path/to/second.jsonl"
    destinations:
      telegram: []
      slack: []
"""
        tmp_config_path.write_text(yaml_content)
        sessions = config_manager.load()

        assert len(sessions) == 2

        # Check session with destinations
        session_001 = next(s for s in sessions if s.session_id == "session-001")
        assert session_001.path == Path("/path/to/first.jsonl")
        assert len(session_001.destinations.telegram) == 1
        assert session_001.destinations.telegram[0].chat_id == "123456789"
        assert len(session_001.destinations.slack) == 1
        assert session_001.destinations.slack[0].channel == "C0123456789"

        # Check session without destinations
        session_002 = next(s for s in sessions if s.session_id == "session-002")
        assert session_002.destinations.telegram == []
        assert session_002.destinations.slack == []

        # Check bot config
        bot_config = config_manager.get_bot_config()
        assert bot_config.telegram_token == "BOT_TOKEN"
        assert bot_config.slack_token == "xoxb-token"

    def test_migration_does_not_write_file(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """Loading old format does not auto-migrate on disk."""
        yaml_content = """sessions:
  - id: "session-001"
    path: "/path/to/first.jsonl"
"""
        tmp_config_path.write_text(yaml_content)
        config_manager.load()

        # File should still be in old format
        content = tmp_config_path.read_text()
        assert "- id:" in content


# ---------------------------------------------------------------------------
# ConfigManager save format tests
# ---------------------------------------------------------------------------


class TestConfigManagerSaveFormat:
    """Tests for saving in new config format."""

    def test_save_writes_new_format(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        tmp_config_path: Path,
    ) -> None:
        """save() writes config in new format."""
        destinations = SessionDestinations(
            telegram=[TelegramDestination(chat_id="123")],
            slack=[SlackDestination(channel="C123")],
        )
        sessions = [
            SessionConfig(
                session_id="test-session",
                path=sample_session_file,
                destinations=destinations,
            )
        ]
        config_manager.save(sessions)

        content = tmp_config_path.read_text()
        # New format uses session_id as key, not "- id:"
        assert "test-session:" in content
        assert "- id:" not in content
        assert "destinations:" in content
        assert "chat_id:" in content
        assert "channel:" in content

    def test_save_includes_bot_config(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        tmp_config_path: Path,
    ) -> None:
        """save() includes bot configuration."""
        config_manager.set_bot_config(
            BotConfig(telegram_token="BOT_TOKEN", slack_token="xoxb-token")
        )
        sessions = [
            SessionConfig(session_id="test-session", path=sample_session_file)
        ]
        config_manager.save(sessions)

        content = tmp_config_path.read_text()
        assert "bots:" in content
        assert "BOT_TOKEN" in content
        assert "xoxb-token" in content


# ---------------------------------------------------------------------------
# ConfigManager bot config tests
# ---------------------------------------------------------------------------


class TestConfigManagerBotConfig:
    """Tests for bot configuration methods."""

    def test_get_bot_config_empty(
        self, config_manager: ConfigManager
    ) -> None:
        """get_bot_config returns empty config when no file."""
        config_manager.load()
        bot_config = config_manager.get_bot_config()
        assert bot_config.telegram_token is None
        assert bot_config.slack_token is None

    def test_get_bot_config_from_file(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """get_bot_config returns tokens from config file."""
        yaml_content = """bots:
  telegram:
    token: "BOT_TOKEN"
  slack:
    token: "xoxb-token"
sessions: {}
"""
        tmp_config_path.write_text(yaml_content)
        config_manager.load()

        bot_config = config_manager.get_bot_config()
        assert bot_config.telegram_token == "BOT_TOKEN"
        assert bot_config.slack_token == "xoxb-token"

    def test_set_bot_config(
        self, config_manager: ConfigManager
    ) -> None:
        """set_bot_config updates in-memory config."""
        new_config = BotConfig(telegram_token="NEW_TOKEN")
        config_manager.set_bot_config(new_config)

        bot_config = config_manager.get_bot_config()
        assert bot_config.telegram_token == "NEW_TOKEN"
        assert bot_config.slack_token is None

    def test_bot_config_persists_on_save(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        tmp_config_path: Path,
    ) -> None:
        """Bot config is persisted when save() is called."""
        config_manager.set_bot_config(BotConfig(telegram_token="BOT_TOKEN"))
        config_manager.save(
            [SessionConfig(session_id="test", path=sample_session_file)]
        )

        # Create new manager and load
        new_manager = ConfigManager(tmp_config_path)
        new_manager.load()
        bot_config = new_manager.get_bot_config()
        assert bot_config.telegram_token == "BOT_TOKEN"


# ---------------------------------------------------------------------------
# ConfigManager get_destinations tests
# ---------------------------------------------------------------------------


class TestConfigManagerGetDestinations:
    """Tests for ConfigManager.get_destinations()."""

    def test_get_destinations_returns_destinations(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """get_destinations returns SessionDestinations for existing session."""
        destinations = SessionDestinations(
            telegram=[TelegramDestination(chat_id="123")],
            slack=[SlackDestination(channel="C123")],
        )
        sessions = [
            SessionConfig(
                session_id="test-session",
                path=sample_session_file,
                destinations=destinations,
            )
        ]
        config_manager.save(sessions)

        result = config_manager.get_destinations("test-session")
        assert result is not None
        assert len(result.telegram) == 1
        assert result.telegram[0].chat_id == "123"
        assert len(result.slack) == 1
        assert result.slack[0].channel == "C123"

    def test_get_destinations_returns_none_for_nonexistent(
        self, config_manager: ConfigManager
    ) -> None:
        """get_destinations returns None for non-existent session."""
        config_manager.load()
        result = config_manager.get_destinations("nonexistent")
        assert result is None

    def test_get_destinations_empty_by_default(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """New sessions have empty destinations."""
        config_manager.add("test-session", sample_session_file)
        result = config_manager.get_destinations("test-session")
        assert result is not None
        assert result.telegram == []
        assert result.slack == []


# ---------------------------------------------------------------------------
# ConfigManager add_destination tests
# ---------------------------------------------------------------------------


class TestConfigManagerAddDestination:
    """Tests for ConfigManager.add_destination()."""

    def test_add_telegram_destination(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """add_destination adds telegram destination to existing session."""
        config_manager.add("test-session", sample_session_file)

        result = config_manager.add_destination(
            "test-session",
            TelegramDestination(chat_id="123456789"),
        )

        assert result is True
        destinations = config_manager.get_destinations("test-session")
        assert destinations is not None
        assert len(destinations.telegram) == 1
        assert destinations.telegram[0].chat_id == "123456789"

    def test_add_slack_destination(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """add_destination adds slack destination to existing session."""
        config_manager.add("test-session", sample_session_file)

        result = config_manager.add_destination(
            "test-session",
            SlackDestination(channel="C0123456789"),
        )

        assert result is True
        destinations = config_manager.get_destinations("test-session")
        assert destinations is not None
        assert len(destinations.slack) == 1
        assert destinations.slack[0].channel == "C0123456789"

    def test_add_destination_creates_session_if_path_provided(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """add_destination creates session if it doesn't exist and path is provided."""
        result = config_manager.add_destination(
            "new-session",
            TelegramDestination(chat_id="123"),
            path=sample_session_file,
        )

        assert result is True
        session = config_manager.get("new-session")
        assert session is not None
        assert session.path == sample_session_file

    def test_add_destination_returns_false_if_no_session_and_no_path(
        self,
        config_manager: ConfigManager,
    ) -> None:
        """add_destination returns False if session doesn't exist and no path."""
        config_manager.load()
        result = config_manager.add_destination(
            "nonexistent",
            TelegramDestination(chat_id="123"),
        )
        assert result is False

    def test_add_destination_idempotent_telegram(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """Adding same telegram destination twice doesn't create duplicate."""
        config_manager.add("test-session", sample_session_file)

        # Add same destination twice
        config_manager.add_destination(
            "test-session",
            TelegramDestination(chat_id="123"),
        )
        config_manager.add_destination(
            "test-session",
            TelegramDestination(chat_id="123"),
        )

        destinations = config_manager.get_destinations("test-session")
        assert destinations is not None
        assert len(destinations.telegram) == 1

    def test_add_destination_idempotent_slack(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """Adding same slack destination twice doesn't create duplicate."""
        config_manager.add("test-session", sample_session_file)

        # Add same destination twice
        config_manager.add_destination(
            "test-session",
            SlackDestination(channel="C123"),
        )
        config_manager.add_destination(
            "test-session",
            SlackDestination(channel="C123"),
        )

        destinations = config_manager.get_destinations("test-session")
        assert destinations is not None
        assert len(destinations.slack) == 1

    def test_add_destination_multiple_different(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """Can add multiple different destinations."""
        config_manager.add("test-session", sample_session_file)

        config_manager.add_destination(
            "test-session",
            TelegramDestination(chat_id="123"),
        )
        config_manager.add_destination(
            "test-session",
            TelegramDestination(chat_id="456"),
        )
        config_manager.add_destination(
            "test-session",
            SlackDestination(channel="C123"),
        )

        destinations = config_manager.get_destinations("test-session")
        assert destinations is not None
        assert len(destinations.telegram) == 2
        assert len(destinations.slack) == 1

    def test_add_destination_validates_empty_telegram_chat_id(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """add_destination rejects empty telegram chat_id."""
        config_manager.add("test-session", sample_session_file)

        with pytest.raises(ValueError, match="chat_id must be non-empty"):
            config_manager.add_destination(
                "test-session",
                TelegramDestination(chat_id=""),
            )

    def test_add_destination_validates_empty_slack_channel(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """add_destination rejects empty slack channel."""
        config_manager.add("test-session", sample_session_file)

        with pytest.raises(ValueError, match="channel must be non-empty"):
            config_manager.add_destination(
                "test-session",
                SlackDestination(channel=""),
            )

    def test_add_destination_validates_path_absolute(
        self,
        config_manager: ConfigManager,
    ) -> None:
        """add_destination rejects non-absolute path."""
        config_manager.load()

        with pytest.raises(ValueError, match="Path must be absolute"):
            config_manager.add_destination(
                "new-session",
                TelegramDestination(chat_id="123"),
                path=Path("relative/path.jsonl"),
            )

    def test_add_destination_validates_path_exists(
        self,
        config_manager: ConfigManager,
        tmp_path: Path,
    ) -> None:
        """add_destination rejects non-existent path."""
        config_manager.load()
        non_existent = tmp_path / "does-not-exist.jsonl"

        with pytest.raises(FileNotFoundError, match="Session file not found"):
            config_manager.add_destination(
                "new-session",
                TelegramDestination(chat_id="123"),
                path=non_existent,
            )


# ---------------------------------------------------------------------------
# ConfigManager remove_destination tests
# ---------------------------------------------------------------------------


class TestConfigManagerRemoveDestination:
    """Tests for ConfigManager.remove_destination()."""

    def test_remove_telegram_destination(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """remove_destination removes telegram destination."""
        config_manager.add("test-session", sample_session_file)
        config_manager.add_destination(
            "test-session",
            TelegramDestination(chat_id="123"),
        )
        config_manager.add_destination(
            "test-session",
            TelegramDestination(chat_id="456"),
        )

        result = config_manager.remove_destination(
            "test-session",
            TelegramDestination(chat_id="123"),
        )

        assert result is True
        destinations = config_manager.get_destinations("test-session")
        assert destinations is not None
        assert len(destinations.telegram) == 1
        assert destinations.telegram[0].chat_id == "456"

    def test_remove_slack_destination(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """remove_destination removes slack destination."""
        config_manager.add("test-session", sample_session_file)
        config_manager.add_destination(
            "test-session",
            SlackDestination(channel="C123"),
        )
        config_manager.add_destination(
            "test-session",
            SlackDestination(channel="C456"),
        )

        result = config_manager.remove_destination(
            "test-session",
            SlackDestination(channel="C123"),
        )

        assert result is True
        destinations = config_manager.get_destinations("test-session")
        assert destinations is not None
        assert len(destinations.slack) == 1
        assert destinations.slack[0].channel == "C456"

    def test_remove_destination_returns_false_for_nonexistent_session(
        self,
        config_manager: ConfigManager,
    ) -> None:
        """remove_destination returns False for non-existent session."""
        config_manager.load()
        result = config_manager.remove_destination(
            "nonexistent",
            TelegramDestination(chat_id="123"),
        )
        assert result is False

    def test_remove_destination_returns_false_for_nonexistent_destination(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """remove_destination returns False for non-existent destination."""
        config_manager.add("test-session", sample_session_file)

        result = config_manager.remove_destination(
            "test-session",
            TelegramDestination(chat_id="nonexistent"),
        )
        assert result is False

    def test_remove_only_destination(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
    ) -> None:
        """remove_destination can remove the only destination."""
        config_manager.add("test-session", sample_session_file)
        config_manager.add_destination(
            "test-session",
            TelegramDestination(chat_id="123"),
        )

        result = config_manager.remove_destination(
            "test-session",
            TelegramDestination(chat_id="123"),
        )

        assert result is True
        destinations = config_manager.get_destinations("test-session")
        assert destinations is not None
        assert destinations.telegram == []


# ---------------------------------------------------------------------------
# Integration: Old format → New format migration
# ---------------------------------------------------------------------------


class TestConfigMigrationRoundtrip:
    """Tests for migrating old format config and saving in new format."""

    def test_load_old_save_new_roundtrip(
        self,
        config_manager: ConfigManager,
        tmp_config_path: Path,
    ) -> None:
        """Loading old format and saving produces valid new format."""
        old_yaml = """sessions:
  - id: "session-001"
    path: "/path/to/first.jsonl"
  - id: "session-002"
    path: "/path/to/second.jsonl"
"""
        tmp_config_path.write_text(old_yaml)

        # Load old format
        sessions = config_manager.load()
        assert len(sessions) == 2

        # Save (writes new format)
        config_manager.save(sessions)

        # Load again - should work with new format
        sessions2 = config_manager.load()
        assert len(sessions2) == 2
        assert {s.session_id for s in sessions2} == {"session-001", "session-002"}

        # Verify new format in file
        content = tmp_config_path.read_text()
        assert "session-001:" in content
        assert "- id:" not in content

    def test_add_destinations_after_migration(
        self,
        config_manager: ConfigManager,
        tmp_config_path: Path,
        sample_session_file: Path,
    ) -> None:
        """Can add destinations to migrated sessions."""
        # Create old format with a real file path
        old_yaml = f"""sessions:
  - id: "test-session"
    path: "{sample_session_file}"
"""
        tmp_config_path.write_text(old_yaml)

        # Load (migrates in memory)
        sessions = config_manager.load()
        assert len(sessions) == 1
        assert sessions[0].destinations.telegram == []

        # Save to convert to new format
        config_manager.save(sessions)

        # Now add destinations
        config_manager.add_destination(
            "test-session",
            TelegramDestination(chat_id="123"),
        )

        # Verify
        destinations = config_manager.get_destinations("test-session")
        assert destinations is not None
        assert len(destinations.telegram) == 1
