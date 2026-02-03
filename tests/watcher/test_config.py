"""Tests for ConfigManager and SessionConfig."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from claude_session_player.watcher.config import (
    BotConfig,
    ConfigManager,
    IndexConfig,
    SearchConfig,
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


# ---------------------------------------------------------------------------
# IndexConfig tests
# ---------------------------------------------------------------------------


class TestIndexConfig:
    """Tests for IndexConfig dataclass."""

    def test_create_with_defaults(self) -> None:
        """IndexConfig has correct default values."""
        config = IndexConfig()
        assert config.paths == ["~/.claude/projects"]
        assert config.refresh_interval == 300
        assert config.max_sessions_per_project == 100
        assert config.include_subagents is False
        assert config.persist is True

    def test_create_with_custom_values(self) -> None:
        """Can create IndexConfig with custom values."""
        config = IndexConfig(
            paths=["/custom/path", "~/projects"],
            refresh_interval=600,
            max_sessions_per_project=50,
            include_subagents=True,
            persist=False,
        )
        assert config.paths == ["/custom/path", "~/projects"]
        assert config.refresh_interval == 600
        assert config.max_sessions_per_project == 50
        assert config.include_subagents is True
        assert config.persist is False

    def test_to_dict(self) -> None:
        """to_dict returns expected structure."""
        config = IndexConfig(
            paths=["/path/one", "/path/two"],
            refresh_interval=120,
        )
        result = config.to_dict()
        assert result == {
            "paths": ["/path/one", "/path/two"],
            "refresh_interval": 120,
            "max_sessions_per_project": 100,
            "include_subagents": False,
            "persist": True,
        }

    def test_from_dict(self) -> None:
        """from_dict reconstructs IndexConfig correctly."""
        data = {
            "paths": ["/custom/path"],
            "refresh_interval": 600,
            "max_sessions_per_project": 200,
            "include_subagents": True,
            "persist": False,
        }
        config = IndexConfig.from_dict(data)
        assert config.paths == ["/custom/path"]
        assert config.refresh_interval == 600
        assert config.max_sessions_per_project == 200
        assert config.include_subagents is True
        assert config.persist is False

    def test_from_dict_with_defaults(self) -> None:
        """from_dict uses defaults for missing keys."""
        config = IndexConfig.from_dict({})
        assert config.paths == ["~/.claude/projects"]
        assert config.refresh_interval == 300
        assert config.max_sessions_per_project == 100
        assert config.include_subagents is False
        assert config.persist is True

    def test_from_dict_partial(self) -> None:
        """from_dict handles partial config."""
        config = IndexConfig.from_dict({"refresh_interval": 60})
        assert config.paths == ["~/.claude/projects"]
        assert config.refresh_interval == 60
        assert config.max_sessions_per_project == 100

    def test_roundtrip(self) -> None:
        """to_dict/from_dict round-trip preserves data."""
        original = IndexConfig(
            paths=["/path/one", "~/path/two"],
            refresh_interval=120,
            max_sessions_per_project=50,
            include_subagents=True,
            persist=False,
        )
        restored = IndexConfig.from_dict(original.to_dict())
        assert restored.paths == original.paths
        assert restored.refresh_interval == original.refresh_interval
        assert restored.max_sessions_per_project == original.max_sessions_per_project
        assert restored.include_subagents == original.include_subagents
        assert restored.persist == original.persist

    def test_expand_paths(self, tmp_path: Path) -> None:
        """expand_paths expands ~ and resolves paths."""
        config = IndexConfig(paths=["~/.claude/projects", str(tmp_path)])
        expanded = config.expand_paths()
        assert len(expanded) == 2
        # First path should have ~ expanded
        assert "~" not in str(expanded[0])
        assert expanded[0].is_absolute()
        # Second path should be resolved
        assert expanded[1] == tmp_path.resolve()


# ---------------------------------------------------------------------------
# SearchConfig tests
# ---------------------------------------------------------------------------


class TestSearchConfig:
    """Tests for SearchConfig dataclass."""

    def test_create_with_defaults(self) -> None:
        """SearchConfig has correct default values."""
        config = SearchConfig()
        assert config.default_limit == 5
        assert config.max_limit == 10
        assert config.default_sort == "recent"
        assert config.state_ttl_seconds == 300

    def test_create_with_custom_values(self) -> None:
        """Can create SearchConfig with custom values."""
        config = SearchConfig(
            default_limit=10,
            max_limit=20,
            default_sort="oldest",
            state_ttl_seconds=600,
        )
        assert config.default_limit == 10
        assert config.max_limit == 20
        assert config.default_sort == "oldest"
        assert config.state_ttl_seconds == 600

    def test_to_dict(self) -> None:
        """to_dict returns expected structure."""
        config = SearchConfig(
            default_limit=3,
            max_limit=15,
            default_sort="size",
            state_ttl_seconds=120,
        )
        result = config.to_dict()
        assert result == {
            "default_limit": 3,
            "max_limit": 15,
            "default_sort": "size",
            "state_ttl_seconds": 120,
        }

    def test_from_dict(self) -> None:
        """from_dict reconstructs SearchConfig correctly."""
        data = {
            "default_limit": 8,
            "max_limit": 25,
            "default_sort": "duration",
            "state_ttl_seconds": 900,
        }
        config = SearchConfig.from_dict(data)
        assert config.default_limit == 8
        assert config.max_limit == 25
        assert config.default_sort == "duration"
        assert config.state_ttl_seconds == 900

    def test_from_dict_with_defaults(self) -> None:
        """from_dict uses defaults for missing keys."""
        config = SearchConfig.from_dict({})
        assert config.default_limit == 5
        assert config.max_limit == 10
        assert config.default_sort == "recent"
        assert config.state_ttl_seconds == 300

    def test_from_dict_partial(self) -> None:
        """from_dict handles partial config."""
        config = SearchConfig.from_dict({"default_limit": 3})
        assert config.default_limit == 3
        assert config.max_limit == 10
        assert config.default_sort == "recent"

    def test_roundtrip(self) -> None:
        """to_dict/from_dict round-trip preserves data."""
        original = SearchConfig(
            default_limit=7,
            max_limit=15,
            default_sort="size",
            state_ttl_seconds=450,
        )
        restored = SearchConfig.from_dict(original.to_dict())
        assert restored.default_limit == original.default_limit
        assert restored.max_limit == original.max_limit
        assert restored.default_sort == original.default_sort
        assert restored.state_ttl_seconds == original.state_ttl_seconds


# ---------------------------------------------------------------------------
# migrate_config tests
# ---------------------------------------------------------------------------


class TestMigrateConfig:
    """Tests for migrate_config function."""

    def test_adds_index_config_if_missing(self) -> None:
        """migrate_config adds default index config when missing."""
        from claude_session_player.watcher.config import migrate_config

        config: dict = {"bots": {}, "sessions": {}}
        result = migrate_config(config)

        assert "index" in result
        assert result["index"]["paths"] == ["~/.claude/projects"]
        assert result["index"]["refresh_interval"] == 300
        assert result["index"]["max_sessions_per_project"] == 100
        assert result["index"]["include_subagents"] is False
        assert result["index"]["persist"] is True

    def test_adds_search_config_if_missing(self) -> None:
        """migrate_config adds default search config when missing."""
        from claude_session_player.watcher.config import migrate_config

        config: dict = {"bots": {}, "sessions": {}}
        result = migrate_config(config)

        assert "search" in result
        assert result["search"]["default_limit"] == 5
        assert result["search"]["max_limit"] == 10
        assert result["search"]["default_sort"] == "recent"
        assert result["search"]["state_ttl_seconds"] == 300

    def test_preserves_existing_index_config(self) -> None:
        """migrate_config preserves existing index config."""
        from claude_session_player.watcher.config import migrate_config

        config: dict = {
            "bots": {},
            "sessions": {},
            "index": {
                "paths": ["/custom/path"],
                "refresh_interval": 60,
            },
        }
        result = migrate_config(config)

        assert result["index"]["paths"] == ["/custom/path"]
        assert result["index"]["refresh_interval"] == 60

    def test_preserves_existing_search_config(self) -> None:
        """migrate_config preserves existing search config."""
        from claude_session_player.watcher.config import migrate_config

        config: dict = {
            "bots": {},
            "sessions": {},
            "search": {
                "default_limit": 3,
                "max_limit": 20,
            },
        }
        result = migrate_config(config)

        assert result["search"]["default_limit"] == 3
        assert result["search"]["max_limit"] == 20

    def test_adds_telegram_mode_if_missing(self) -> None:
        """migrate_config adds mode to telegram config if missing."""
        from claude_session_player.watcher.config import migrate_config

        config: dict = {
            "bots": {"telegram": {"token": "BOT_TOKEN"}},
            "sessions": {},
        }
        result = migrate_config(config)

        assert result["bots"]["telegram"]["mode"] == "webhook"

    def test_preserves_existing_telegram_mode(self) -> None:
        """migrate_config preserves existing telegram mode."""
        from claude_session_player.watcher.config import migrate_config

        config: dict = {
            "bots": {"telegram": {"token": "BOT_TOKEN", "mode": "polling"}},
            "sessions": {},
        }
        result = migrate_config(config)

        assert result["bots"]["telegram"]["mode"] == "polling"

    def test_handles_empty_telegram_config(self) -> None:
        """migrate_config handles None/empty telegram config."""
        from claude_session_player.watcher.config import migrate_config

        config: dict = {
            "bots": {"telegram": None},
            "sessions": {},
        }
        result = migrate_config(config)

        # Should not crash, telegram remains None
        assert result["bots"]["telegram"] is None


# ---------------------------------------------------------------------------
# apply_env_overrides tests
# ---------------------------------------------------------------------------


class TestApplyEnvOverrides:
    """Tests for apply_env_overrides function."""

    def test_overrides_index_paths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLAUDE_INDEX_PATHS overrides index paths."""
        from claude_session_player.watcher.config import apply_env_overrides

        monkeypatch.setenv("CLAUDE_INDEX_PATHS", "/path/one,/path/two")

        config: dict = {"index": {"paths": ["~/.claude/projects"]}}
        result = apply_env_overrides(config)

        assert result["index"]["paths"] == ["/path/one", "/path/two"]

    def test_overrides_refresh_interval(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLAUDE_INDEX_REFRESH_INTERVAL overrides refresh interval."""
        from claude_session_player.watcher.config import apply_env_overrides

        monkeypatch.setenv("CLAUDE_INDEX_REFRESH_INTERVAL", "60")

        config: dict = {"index": {"refresh_interval": 300}}
        result = apply_env_overrides(config)

        assert result["index"]["refresh_interval"] == 60

    def test_ignores_invalid_refresh_interval(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid CLAUDE_INDEX_REFRESH_INTERVAL is ignored."""
        from claude_session_player.watcher.config import apply_env_overrides

        monkeypatch.setenv("CLAUDE_INDEX_REFRESH_INTERVAL", "not-a-number")

        config: dict = {"index": {"refresh_interval": 300}}
        result = apply_env_overrides(config)

        # Should keep original value
        assert result["index"]["refresh_interval"] == 300

    def test_overrides_telegram_webhook_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TELEGRAM_WEBHOOK_URL overrides webhook URL."""
        from claude_session_player.watcher.config import apply_env_overrides

        monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://example.com/webhook")

        config: dict = {"bots": {"telegram": {"token": "BOT_TOKEN"}}}
        result = apply_env_overrides(config)

        assert result["bots"]["telegram"]["webhook_url"] == "https://example.com/webhook"

    def test_creates_telegram_section_if_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TELEGRAM_WEBHOOK_URL creates telegram section if missing."""
        from claude_session_player.watcher.config import apply_env_overrides

        monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://example.com/webhook")

        config: dict = {}
        result = apply_env_overrides(config)

        assert result["bots"]["telegram"]["webhook_url"] == "https://example.com/webhook"

    def test_creates_index_section_if_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment overrides create index section if missing."""
        from claude_session_player.watcher.config import apply_env_overrides

        monkeypatch.setenv("CLAUDE_INDEX_PATHS", "/custom/path")

        config: dict = {}
        result = apply_env_overrides(config)

        assert result["index"]["paths"] == ["/custom/path"]

    def test_strips_whitespace_from_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLAUDE_INDEX_PATHS strips whitespace from paths."""
        from claude_session_player.watcher.config import apply_env_overrides

        monkeypatch.setenv("CLAUDE_INDEX_PATHS", " /path/one , /path/two ")

        config: dict = {"index": {}}
        result = apply_env_overrides(config)

        assert result["index"]["paths"] == ["/path/one", "/path/two"]


# ---------------------------------------------------------------------------
# expand_paths tests
# ---------------------------------------------------------------------------


class TestExpandPaths:
    """Tests for expand_paths function."""

    def test_expands_tilde(self) -> None:
        """expand_paths expands ~ to home directory."""
        from claude_session_player.watcher.config import expand_paths

        result = expand_paths(["~/.claude/projects"])
        assert len(result) == 1
        assert "~" not in str(result[0])
        assert result[0].is_absolute()

    def test_resolves_relative_paths(self, tmp_path: Path) -> None:
        """expand_paths resolves relative paths."""
        from claude_session_player.watcher.config import expand_paths

        # Create a subdir to test resolution
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        result = expand_paths([str(subdir)])
        assert result[0].is_absolute()
        assert result[0] == subdir.resolve()

    def test_handles_multiple_paths(self) -> None:
        """expand_paths handles multiple paths."""
        from claude_session_player.watcher.config import expand_paths

        result = expand_paths(["~/.claude/projects", "/absolute/path"])
        assert len(result) == 2
        assert all(p.is_absolute() for p in result)

    def test_handles_empty_list(self) -> None:
        """expand_paths handles empty list."""
        from claude_session_player.watcher.config import expand_paths

        result = expand_paths([])
        assert result == []


# ---------------------------------------------------------------------------
# ConfigManager index/search config tests
# ---------------------------------------------------------------------------


class TestConfigManagerIndexConfig:
    """Tests for ConfigManager index configuration methods."""

    def test_get_index_config_defaults(
        self, config_manager: ConfigManager
    ) -> None:
        """get_index_config returns defaults when no file."""
        config_manager.load()
        index_config = config_manager.get_index_config()
        assert index_config.paths == ["~/.claude/projects"]
        assert index_config.refresh_interval == 300

    def test_get_index_config_from_file(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """get_index_config returns values from config file."""
        yaml_content = """index:
  paths:
    - "/custom/path"
  refresh_interval: 60
  max_sessions_per_project: 50
  include_subagents: true
  persist: false
sessions: {}
"""
        tmp_config_path.write_text(yaml_content)
        config_manager.load()

        index_config = config_manager.get_index_config()
        assert index_config.paths == ["/custom/path"]
        assert index_config.refresh_interval == 60
        assert index_config.max_sessions_per_project == 50
        assert index_config.include_subagents is True
        assert index_config.persist is False

    def test_set_index_config(
        self, config_manager: ConfigManager
    ) -> None:
        """set_index_config updates in-memory config."""
        new_config = IndexConfig(
            paths=["/new/path"],
            refresh_interval=120,
        )
        config_manager.set_index_config(new_config)

        index_config = config_manager.get_index_config()
        assert index_config.paths == ["/new/path"]
        assert index_config.refresh_interval == 120

    def test_index_config_persists_on_save(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        tmp_config_path: Path,
    ) -> None:
        """Index config is persisted when save() is called."""
        config_manager.set_index_config(
            IndexConfig(paths=["/custom/path"], refresh_interval=60)
        )
        config_manager.save(
            [SessionConfig(session_id="test", path=sample_session_file)]
        )

        # Create new manager and load
        new_manager = ConfigManager(tmp_config_path)
        new_manager.load()
        index_config = new_manager.get_index_config()
        assert index_config.paths == ["/custom/path"]
        assert index_config.refresh_interval == 60


class TestConfigManagerSearchConfig:
    """Tests for ConfigManager search configuration methods."""

    def test_get_search_config_defaults(
        self, config_manager: ConfigManager
    ) -> None:
        """get_search_config returns defaults when no file."""
        config_manager.load()
        search_config = config_manager.get_search_config()
        assert search_config.default_limit == 5
        assert search_config.max_limit == 10
        assert search_config.default_sort == "recent"
        assert search_config.state_ttl_seconds == 300

    def test_get_search_config_from_file(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """get_search_config returns values from config file."""
        yaml_content = """search:
  default_limit: 3
  max_limit: 20
  default_sort: size
  state_ttl_seconds: 600
sessions: {}
"""
        tmp_config_path.write_text(yaml_content)
        config_manager.load()

        search_config = config_manager.get_search_config()
        assert search_config.default_limit == 3
        assert search_config.max_limit == 20
        assert search_config.default_sort == "size"
        assert search_config.state_ttl_seconds == 600

    def test_set_search_config(
        self, config_manager: ConfigManager
    ) -> None:
        """set_search_config updates in-memory config."""
        new_config = SearchConfig(
            default_limit=8,
            max_limit=25,
        )
        config_manager.set_search_config(new_config)

        search_config = config_manager.get_search_config()
        assert search_config.default_limit == 8
        assert search_config.max_limit == 25

    def test_search_config_persists_on_save(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        tmp_config_path: Path,
    ) -> None:
        """Search config is persisted when save() is called."""
        config_manager.set_search_config(
            SearchConfig(default_limit=8, max_limit=25)
        )
        config_manager.save(
            [SessionConfig(session_id="test", path=sample_session_file)]
        )

        # Create new manager and load
        new_manager = ConfigManager(tmp_config_path)
        new_manager.load()
        search_config = new_manager.get_search_config()
        assert search_config.default_limit == 8
        assert search_config.max_limit == 25


# ---------------------------------------------------------------------------
# ConfigManager config migration integration tests
# ---------------------------------------------------------------------------


class TestConfigManagerMigration:
    """Tests for ConfigManager config migration during load."""

    def test_load_adds_defaults_when_missing(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """load() adds default index/search config when file has none."""
        yaml_content = """bots:
  telegram:
    token: "BOT_TOKEN"
sessions: {}
"""
        tmp_config_path.write_text(yaml_content)
        config_manager.load()

        # Index config should have defaults
        index_config = config_manager.get_index_config()
        assert index_config.paths == ["~/.claude/projects"]
        assert index_config.refresh_interval == 300

        # Search config should have defaults
        search_config = config_manager.get_search_config()
        assert search_config.default_limit == 5
        assert search_config.max_limit == 10

    def test_load_with_env_override(
        self,
        config_manager: ConfigManager,
        tmp_config_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """load() applies environment variable overrides."""
        yaml_content = """index:
  paths:
    - "~/.claude/projects"
  refresh_interval: 300
sessions: {}
"""
        tmp_config_path.write_text(yaml_content)
        monkeypatch.setenv("CLAUDE_INDEX_PATHS", "/env/path")
        monkeypatch.setenv("CLAUDE_INDEX_REFRESH_INTERVAL", "60")

        config_manager.load()

        index_config = config_manager.get_index_config()
        assert index_config.paths == ["/env/path"]
        assert index_config.refresh_interval == 60

    def test_load_all_sections(
        self, config_manager: ConfigManager, tmp_config_path: Path
    ) -> None:
        """load() correctly loads all config sections."""
        yaml_content = """bots:
  telegram:
    token: "BOT_TOKEN"
    mode: polling
  slack:
    token: "xoxb-token"
    signing_secret: "secret123"
index:
  paths:
    - "/custom/path"
  refresh_interval: 120
search:
  default_limit: 7
  max_limit: 15
sessions:
  test-session:
    path: "/path/to/session.jsonl"
    destinations:
      telegram: []
      slack: []
"""
        tmp_config_path.write_text(yaml_content)
        sessions = config_manager.load()

        # Verify all sections loaded
        assert len(sessions) == 1

        bot_config = config_manager.get_bot_config()
        assert bot_config.telegram_token == "BOT_TOKEN"
        assert bot_config.telegram_mode == "polling"
        assert bot_config.slack_token == "xoxb-token"
        assert bot_config.slack_signing_secret == "secret123"

        index_config = config_manager.get_index_config()
        assert index_config.paths == ["/custom/path"]
        assert index_config.refresh_interval == 120

        search_config = config_manager.get_search_config()
        assert search_config.default_limit == 7
        assert search_config.max_limit == 15

    def test_save_includes_all_sections(
        self,
        config_manager: ConfigManager,
        sample_session_file: Path,
        tmp_config_path: Path,
    ) -> None:
        """save() includes all config sections in output."""
        config_manager.set_bot_config(
            BotConfig(telegram_token="BOT_TOKEN", slack_token="xoxb-token")
        )
        config_manager.set_index_config(
            IndexConfig(paths=["/custom/path"], refresh_interval=60)
        )
        config_manager.set_search_config(
            SearchConfig(default_limit=8, max_limit=20)
        )
        config_manager.save(
            [SessionConfig(session_id="test", path=sample_session_file)]
        )

        content = tmp_config_path.read_text()
        assert "bots:" in content
        assert "index:" in content
        assert "search:" in content
        assert "sessions:" in content
        assert "BOT_TOKEN" in content
        assert "/custom/path" in content
        assert "default_limit: 8" in content


# ---------------------------------------------------------------------------
# Integration: Full config file round-trip
# ---------------------------------------------------------------------------


class TestConfigFullRoundtrip:
    """Tests for full config file round-trip with all sections."""

    def test_full_config_roundtrip(
        self,
        tmp_config_path: Path,
        sample_session_file: Path,
    ) -> None:
        """Full config with all sections survives load/save round-trip."""
        # Create config with all sections
        manager1 = ConfigManager(tmp_config_path)
        manager1.set_bot_config(
            BotConfig(
                telegram_token="BOT_TOKEN",
                telegram_mode="polling",
                telegram_webhook_url="https://example.com",
                slack_token="xoxb-token",
                slack_signing_secret="secret123",
            )
        )
        manager1.set_index_config(
            IndexConfig(
                paths=["/path/one", "/path/two"],
                refresh_interval=120,
                max_sessions_per_project=50,
                include_subagents=True,
                persist=False,
            )
        )
        manager1.set_search_config(
            SearchConfig(
                default_limit=8,
                max_limit=25,
                default_sort="size",
                state_ttl_seconds=600,
            )
        )

        # Save with a session
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
        manager1.save(sessions)

        # Load with new manager
        manager2 = ConfigManager(tmp_config_path)
        loaded_sessions = manager2.load()

        # Verify sessions
        assert len(loaded_sessions) == 1
        assert loaded_sessions[0].session_id == "test-session"
        assert len(loaded_sessions[0].destinations.telegram) == 1
        assert len(loaded_sessions[0].destinations.slack) == 1

        # Verify bot config
        bot_config = manager2.get_bot_config()
        assert bot_config.telegram_token == "BOT_TOKEN"
        assert bot_config.telegram_mode == "polling"
        assert bot_config.telegram_webhook_url == "https://example.com"
        assert bot_config.slack_token == "xoxb-token"
        assert bot_config.slack_signing_secret == "secret123"

        # Verify index config
        index_config = manager2.get_index_config()
        assert index_config.paths == ["/path/one", "/path/two"]
        assert index_config.refresh_interval == 120
        assert index_config.max_sessions_per_project == 50
        assert index_config.include_subagents is True
        assert index_config.persist is False

        # Verify search config
        search_config = manager2.get_search_config()
        assert search_config.default_limit == 8
        assert search_config.max_limit == 25
        assert search_config.default_sort == "size"
        assert search_config.state_ttl_seconds == 600
