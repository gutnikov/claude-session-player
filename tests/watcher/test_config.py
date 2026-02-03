"""Tests for ConfigManager and SessionConfig."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from claude_session_player.watcher.config import ConfigManager, SessionConfig


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

    def test_to_dict(self) -> None:
        """to_dict returns expected structure."""
        config = SessionConfig(
            session_id="test-session-001",
            path=Path("/path/to/session.jsonl"),
        )
        result = config.to_dict()
        assert result == {
            "id": "test-session-001",
            "path": "/path/to/session.jsonl",
        }

    def test_from_dict(self) -> None:
        """from_dict reconstructs SessionConfig correctly."""
        data = {
            "id": "test-session-001",
            "path": "/path/to/session.jsonl",
        }
        config = SessionConfig.from_dict(data)
        assert config.session_id == "test-session-001"
        assert config.path == Path("/path/to/session.jsonl")

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
