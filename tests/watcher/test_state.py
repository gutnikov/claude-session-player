"""Tests for StateManager and SessionState."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_session_player.events import ProcessingContext
from claude_session_player.watcher.state import (
    SessionState,
    StateManager,
    _sanitize_session_id,
)


# ---------------------------------------------------------------------------
# SessionState tests
# ---------------------------------------------------------------------------


class TestSessionState:
    """Tests for SessionState dataclass."""

    def test_create_session_state(self) -> None:
        """Can create SessionState with required fields."""
        context = ProcessingContext()
        now = datetime.now(timezone.utc)
        state = SessionState(
            file_position=12345,
            line_number=42,
            processing_context=context,
            last_modified=now,
        )
        assert state.file_position == 12345
        assert state.line_number == 42
        assert state.processing_context == context
        assert state.last_modified == now

    def test_to_dict(self) -> None:
        """to_dict returns expected structure."""
        context = ProcessingContext(
            tool_use_id_to_block_id={"tu_123": "block_456"},
            current_request_id="req_789",
        )
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        state = SessionState(
            file_position=12345,
            line_number=42,
            processing_context=context,
            last_modified=now,
        )

        result = state.to_dict()

        assert result == {
            "file_position": 12345,
            "line_number": 42,
            "processing_context": {
                "tool_use_id_to_block_id": {"tu_123": "block_456"},
                "current_request_id": "req_789",
            },
            "last_modified": "2024-01-15T10:30:00+00:00",
        }

    def test_from_dict(self) -> None:
        """from_dict reconstructs SessionState correctly."""
        data = {
            "file_position": 12345,
            "line_number": 42,
            "processing_context": {
                "tool_use_id_to_block_id": {"tu_123": "block_456"},
                "current_request_id": "req_789",
            },
            "last_modified": "2024-01-15T10:30:00+00:00",
        }

        state = SessionState.from_dict(data)

        assert state.file_position == 12345
        assert state.line_number == 42
        assert state.processing_context.tool_use_id_to_block_id == {"tu_123": "block_456"}
        assert state.processing_context.current_request_id == "req_789"
        assert state.last_modified == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_roundtrip(self) -> None:
        """to_dict/from_dict round-trip preserves data."""
        context = ProcessingContext(
            tool_use_id_to_block_id={"tu_123": "block_456", "tu_abc": "block_def"},
            current_request_id="req_789",
        )
        now = datetime.now(timezone.utc)
        original = SessionState(
            file_position=99999,
            line_number=100,
            processing_context=context,
            last_modified=now,
        )

        restored = SessionState.from_dict(original.to_dict())

        assert restored.file_position == original.file_position
        assert restored.line_number == original.line_number
        assert (
            restored.processing_context.tool_use_id_to_block_id
            == original.processing_context.tool_use_id_to_block_id
        )
        assert (
            restored.processing_context.current_request_id
            == original.processing_context.current_request_id
        )
        assert restored.last_modified == original.last_modified

    def test_roundtrip_with_empty_context(self) -> None:
        """to_dict/from_dict round-trip works with empty ProcessingContext."""
        context = ProcessingContext()
        now = datetime.now(timezone.utc)
        original = SessionState(
            file_position=0,
            line_number=0,
            processing_context=context,
            last_modified=now,
        )

        restored = SessionState.from_dict(original.to_dict())

        assert restored.file_position == 0
        assert restored.line_number == 0
        assert restored.processing_context.tool_use_id_to_block_id == {}
        assert restored.processing_context.current_request_id is None


# ---------------------------------------------------------------------------
# _sanitize_session_id tests
# ---------------------------------------------------------------------------


class TestSanitizeSessionId:
    """Tests for _sanitize_session_id helper function."""

    def test_normal_id_unchanged(self) -> None:
        """Normal session IDs pass through unchanged."""
        assert _sanitize_session_id("014d9d94-abc123") == "014d9d94-abc123"

    def test_uuid_unchanged(self) -> None:
        """UUID format passes through unchanged."""
        assert (
            _sanitize_session_id("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
            == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        )

    def test_replaces_windows_forbidden_chars(self) -> None:
        """Replaces characters forbidden on Windows."""
        assert _sanitize_session_id('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"

    def test_collapses_multiple_underscores(self) -> None:
        """Multiple consecutive underscores collapsed to one."""
        assert _sanitize_session_id("a::b//c") == "a_b_c"

    def test_strips_leading_trailing_underscores(self) -> None:
        """Strips leading and trailing underscores."""
        assert _sanitize_session_id("/abc/") == "abc"

    def test_strips_leading_trailing_dots(self) -> None:
        """Strips leading and trailing dots."""
        assert _sanitize_session_id(".abc.") == "abc"

    def test_empty_string_becomes_underscore(self) -> None:
        """Empty string after sanitization becomes underscore."""
        assert _sanitize_session_id(":::") == "_"

    def test_replaces_control_characters(self) -> None:
        """Control characters are replaced."""
        assert _sanitize_session_id("abc\x00def\x1fghi") == "abc_def_ghi"


# ---------------------------------------------------------------------------
# StateManager fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """Return path to state directory in temp directory."""
    return tmp_path / "state"


@pytest.fixture
def state_manager(state_dir: Path) -> StateManager:
    """Create StateManager with temp state directory."""
    return StateManager(state_dir)


@pytest.fixture
def sample_state() -> SessionState:
    """Create a sample SessionState for testing."""
    context = ProcessingContext(
        tool_use_id_to_block_id={"tu_123": "block_456"},
        current_request_id="req_789",
    )
    return SessionState(
        file_position=12345,
        line_number=42,
        processing_context=context,
        last_modified=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# StateManager.save tests
# ---------------------------------------------------------------------------


class TestStateManagerSave:
    """Tests for StateManager.save()."""

    def test_save_creates_state_file(
        self,
        state_manager: StateManager,
        state_dir: Path,
        sample_state: SessionState,
    ) -> None:
        """save() creates state file with correct JSON."""
        state_manager.save("session-001", sample_state)

        state_path = state_dir / "session-001.json"
        assert state_path.exists()

        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["file_position"] == 12345
        assert data["line_number"] == 42
        assert data["processing_context"]["tool_use_id_to_block_id"] == {
            "tu_123": "block_456"
        }
        assert data["processing_context"]["current_request_id"] == "req_789"
        assert data["last_modified"] == "2024-01-15T10:30:00+00:00"

    def test_save_creates_state_directory(
        self,
        state_manager: StateManager,
        state_dir: Path,
        sample_state: SessionState,
    ) -> None:
        """save() creates state directory if missing."""
        assert not state_dir.exists()

        state_manager.save("session-001", sample_state)

        assert state_dir.exists()
        assert (state_dir / "session-001.json").exists()

    def test_save_creates_nested_state_directory(
        self,
        tmp_path: Path,
        sample_state: SessionState,
    ) -> None:
        """save() creates nested state directory if missing."""
        nested_dir = tmp_path / "nested" / "state" / "dir"
        manager = StateManager(nested_dir)

        manager.save("session-001", sample_state)

        assert nested_dir.exists()
        assert (nested_dir / "session-001.json").exists()

    def test_save_overwrites_existing_state(
        self,
        state_manager: StateManager,
        state_dir: Path,
    ) -> None:
        """save() overwrites existing state file."""
        context1 = ProcessingContext(current_request_id="old_req")
        state1 = SessionState(
            file_position=100,
            line_number=1,
            processing_context=context1,
            last_modified=datetime.now(timezone.utc),
        )
        state_manager.save("session-001", state1)

        context2 = ProcessingContext(current_request_id="new_req")
        state2 = SessionState(
            file_position=200,
            line_number=2,
            processing_context=context2,
            last_modified=datetime.now(timezone.utc),
        )
        state_manager.save("session-001", state2)

        loaded = state_manager.load("session-001")
        assert loaded is not None
        assert loaded.file_position == 200
        assert loaded.processing_context.current_request_id == "new_req"

    def test_save_sanitizes_session_id(
        self,
        state_manager: StateManager,
        state_dir: Path,
        sample_state: SessionState,
    ) -> None:
        """save() sanitizes session ID for filesystem safety."""
        state_manager.save("session/with:invalid*chars", sample_state)

        # Should create file with sanitized name
        state_path = state_dir / "session_with_invalid_chars.json"
        assert state_path.exists()


# ---------------------------------------------------------------------------
# StateManager.load tests
# ---------------------------------------------------------------------------


class TestStateManagerLoad:
    """Tests for StateManager.load()."""

    def test_load_returns_correct_session_state(
        self,
        state_manager: StateManager,
        sample_state: SessionState,
    ) -> None:
        """load() returns correct SessionState."""
        state_manager.save("session-001", sample_state)

        loaded = state_manager.load("session-001")

        assert loaded is not None
        assert loaded.file_position == 12345
        assert loaded.line_number == 42
        assert loaded.processing_context.tool_use_id_to_block_id == {
            "tu_123": "block_456"
        }
        assert loaded.processing_context.current_request_id == "req_789"
        assert loaded.last_modified == datetime(
            2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc
        )

    def test_load_missing_state_file_returns_none(
        self,
        state_manager: StateManager,
    ) -> None:
        """load() returns None when state file doesn't exist."""
        result = state_manager.load("nonexistent-session")
        assert result is None

    def test_load_corrupt_json_returns_none(
        self,
        state_manager: StateManager,
        state_dir: Path,
    ) -> None:
        """load() returns None for corrupt JSON file."""
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / "session-001.json"
        state_path.write_text("not valid json {{{")

        result = state_manager.load("session-001")

        assert result is None

    def test_load_missing_fields_returns_none(
        self,
        state_manager: StateManager,
        state_dir: Path,
    ) -> None:
        """load() returns None when required fields are missing."""
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / "session-001.json"
        state_path.write_text('{"file_position": 123}')  # Missing other fields

        result = state_manager.load("session-001")

        assert result is None

    def test_load_invalid_datetime_returns_none(
        self,
        state_manager: StateManager,
        state_dir: Path,
    ) -> None:
        """load() returns None when datetime is invalid."""
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / "session-001.json"
        data = {
            "file_position": 123,
            "line_number": 1,
            "processing_context": {
                "tool_use_id_to_block_id": {},
                "current_request_id": None,
            },
            "last_modified": "not-a-date",
        }
        state_path.write_text(json.dumps(data))

        result = state_manager.load("session-001")

        assert result is None

    def test_load_with_sanitized_session_id(
        self,
        state_manager: StateManager,
        sample_state: SessionState,
    ) -> None:
        """load() can load state saved with sanitized session ID."""
        state_manager.save("session/with:invalid*chars", sample_state)

        loaded = state_manager.load("session/with:invalid*chars")

        assert loaded is not None
        assert loaded.file_position == 12345


# ---------------------------------------------------------------------------
# StateManager.delete tests
# ---------------------------------------------------------------------------


class TestStateManagerDelete:
    """Tests for StateManager.delete()."""

    def test_delete_removes_state_file(
        self,
        state_manager: StateManager,
        state_dir: Path,
        sample_state: SessionState,
    ) -> None:
        """delete() removes the state file."""
        state_manager.save("session-001", sample_state)
        state_path = state_dir / "session-001.json"
        assert state_path.exists()

        state_manager.delete("session-001")

        assert not state_path.exists()

    def test_delete_nonexistent_file_no_error(
        self,
        state_manager: StateManager,
    ) -> None:
        """delete() does nothing for non-existent file (no error)."""
        # Should not raise any exception
        state_manager.delete("nonexistent-session")

    def test_delete_with_sanitized_session_id(
        self,
        state_manager: StateManager,
        state_dir: Path,
        sample_state: SessionState,
    ) -> None:
        """delete() removes state file for sanitized session ID."""
        state_manager.save("session/with:invalid*chars", sample_state)
        state_path = state_dir / "session_with_invalid_chars.json"
        assert state_path.exists()

        state_manager.delete("session/with:invalid*chars")

        assert not state_path.exists()


# ---------------------------------------------------------------------------
# StateManager.exists tests
# ---------------------------------------------------------------------------


class TestStateManagerExists:
    """Tests for StateManager.exists()."""

    def test_exists_returns_true_for_existing_state(
        self,
        state_manager: StateManager,
        sample_state: SessionState,
    ) -> None:
        """exists() returns True when state file exists."""
        state_manager.save("session-001", sample_state)

        assert state_manager.exists("session-001") is True

    def test_exists_returns_false_for_missing_state(
        self,
        state_manager: StateManager,
    ) -> None:
        """exists() returns False when state file doesn't exist."""
        assert state_manager.exists("nonexistent-session") is False

    def test_exists_returns_false_when_dir_missing(
        self,
        state_manager: StateManager,
        state_dir: Path,
    ) -> None:
        """exists() returns False when state directory doesn't exist."""
        # Don't create state_dir
        assert not state_dir.exists()

        assert state_manager.exists("session-001") is False


# ---------------------------------------------------------------------------
# Save/load round-trip tests
# ---------------------------------------------------------------------------


class TestSaveLoadRoundTrip:
    """Tests for save/load round-trip."""

    def test_roundtrip_preserves_all_fields(
        self,
        state_manager: StateManager,
        sample_state: SessionState,
    ) -> None:
        """save/load round-trip preserves all fields."""
        state_manager.save("session-001", sample_state)

        loaded = state_manager.load("session-001")

        assert loaded is not None
        assert loaded.file_position == sample_state.file_position
        assert loaded.line_number == sample_state.line_number
        assert (
            loaded.processing_context.tool_use_id_to_block_id
            == sample_state.processing_context.tool_use_id_to_block_id
        )
        assert (
            loaded.processing_context.current_request_id
            == sample_state.processing_context.current_request_id
        )
        assert loaded.last_modified == sample_state.last_modified

    def test_roundtrip_with_large_context(
        self,
        state_manager: StateManager,
    ) -> None:
        """save/load round-trip works with large ProcessingContext."""
        # Create context with many mappings
        mappings = {f"tu_{i}": f"block_{i}" for i in range(100)}
        context = ProcessingContext(
            tool_use_id_to_block_id=mappings,
            current_request_id="large_req",
        )
        state = SessionState(
            file_position=999999,
            line_number=5000,
            processing_context=context,
            last_modified=datetime.now(timezone.utc),
        )

        state_manager.save("session-large", state)
        loaded = state_manager.load("session-large")

        assert loaded is not None
        assert len(loaded.processing_context.tool_use_id_to_block_id) == 100
        assert loaded.processing_context.tool_use_id_to_block_id["tu_50"] == "block_50"


# ---------------------------------------------------------------------------
# Datetime serialization tests
# ---------------------------------------------------------------------------


class TestDatetimeSerialization:
    """Tests for datetime serialization/deserialization."""

    def test_utc_datetime_preserves_timezone(
        self,
        state_manager: StateManager,
    ) -> None:
        """UTC datetime preserves timezone info."""
        utc_time = datetime(2024, 6, 15, 14, 30, 45, tzinfo=timezone.utc)
        context = ProcessingContext()
        state = SessionState(
            file_position=0,
            line_number=0,
            processing_context=context,
            last_modified=utc_time,
        )

        state_manager.save("session-utc", state)
        loaded = state_manager.load("session-utc")

        assert loaded is not None
        assert loaded.last_modified == utc_time
        assert loaded.last_modified.tzinfo is not None

    def test_naive_datetime_roundtrip(
        self,
        state_manager: StateManager,
    ) -> None:
        """Naive datetime (no timezone) round-trips correctly."""
        naive_time = datetime(2024, 6, 15, 14, 30, 45)
        context = ProcessingContext()
        state = SessionState(
            file_position=0,
            line_number=0,
            processing_context=context,
            last_modified=naive_time,
        )

        state_manager.save("session-naive", state)
        loaded = state_manager.load("session-naive")

        assert loaded is not None
        # Naive datetime should round-trip (no timezone added/removed)
        assert loaded.last_modified.year == 2024
        assert loaded.last_modified.month == 6
        assert loaded.last_modified.day == 15


# ---------------------------------------------------------------------------
# Atomic write tests
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    """Tests for atomic write functionality."""

    def test_no_temp_files_left_on_success(
        self,
        state_manager: StateManager,
        state_dir: Path,
        sample_state: SessionState,
    ) -> None:
        """No temp files remain after successful save."""
        state_manager.save("session-001", sample_state)

        # Check for any temp files in the directory
        temp_files = list(state_dir.glob(".state_*.json.tmp"))
        assert len(temp_files) == 0

    def test_atomic_write_temp_file_cleaned_on_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        sample_state: SessionState,
    ) -> None:
        """Temp files are cleaned up if write fails mid-operation."""
        state_dir = tmp_path / "state"
        manager = StateManager(state_dir)

        original_fdopen = os.fdopen

        def failing_fdopen(fd: int, mode: str, **kwargs):
            # Close the fd to avoid leak
            os.close(fd)
            raise IOError("Simulated write failure")

        monkeypatch.setattr(os, "fdopen", failing_fdopen)

        with pytest.raises(IOError, match="Simulated write failure"):
            manager.save("session-001", sample_state)

        # Check no temp files left behind (directory may not exist if failure is early)
        if state_dir.exists():
            temp_files = list(state_dir.glob(".state_*.json.tmp"))
            assert len(temp_files) == 0

    def test_state_dir_property(
        self,
        state_dir: Path,
    ) -> None:
        """state_dir property returns the state directory path."""
        manager = StateManager(state_dir)
        assert manager.state_dir == state_dir


# ---------------------------------------------------------------------------
# ProcessingContext nested serialization tests
# ---------------------------------------------------------------------------


class TestProcessingContextNestedSerialization:
    """Tests for ProcessingContext nested serialization in SessionState."""

    def test_empty_context_serialization(
        self,
        state_manager: StateManager,
    ) -> None:
        """Empty ProcessingContext serializes correctly."""
        context = ProcessingContext()
        state = SessionState(
            file_position=0,
            line_number=0,
            processing_context=context,
            last_modified=datetime.now(timezone.utc),
        )

        state_manager.save("session-empty-ctx", state)
        loaded = state_manager.load("session-empty-ctx")

        assert loaded is not None
        assert loaded.processing_context.tool_use_id_to_block_id == {}
        assert loaded.processing_context.current_request_id is None

    def test_context_with_none_request_id(
        self,
        state_manager: StateManager,
    ) -> None:
        """ProcessingContext with None current_request_id serializes correctly."""
        context = ProcessingContext(
            tool_use_id_to_block_id={"tu_1": "b_1"},
            current_request_id=None,
        )
        state = SessionState(
            file_position=100,
            line_number=5,
            processing_context=context,
            last_modified=datetime.now(timezone.utc),
        )

        state_manager.save("session-none-req", state)
        loaded = state_manager.load("session-none-req")

        assert loaded is not None
        assert loaded.processing_context.tool_use_id_to_block_id == {"tu_1": "b_1"}
        assert loaded.processing_context.current_request_id is None

    def test_context_with_string_request_id(
        self,
        state_manager: StateManager,
    ) -> None:
        """ProcessingContext with string current_request_id serializes correctly."""
        context = ProcessingContext(
            tool_use_id_to_block_id={},
            current_request_id="req_abc123",
        )
        state = SessionState(
            file_position=200,
            line_number=10,
            processing_context=context,
            last_modified=datetime.now(timezone.utc),
        )

        state_manager.save("session-str-req", state)
        loaded = state_manager.load("session-str-req")

        assert loaded is not None
        assert loaded.processing_context.current_request_id == "req_abc123"
