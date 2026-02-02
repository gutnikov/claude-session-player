"""Tests for JSONL session file parsing."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from claude_session_player.parser import read_session


@pytest.fixture
def sample_jsonl(tmp_path: Path) -> Path:
    """Create a sample JSONL file."""
    lines = [
        {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "hello"}},
        {"type": "assistant", "uuid": "a1", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}},
        {"type": "system", "uuid": "s1", "subtype": "turn_duration", "durationMs": 1000},
    ]
    file_path = tmp_path / "test.jsonl"
    with open(file_path, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return file_path


@pytest.fixture
def empty_jsonl(tmp_path: Path) -> Path:
    """Create an empty JSONL file."""
    file_path = tmp_path / "empty.jsonl"
    file_path.touch()
    return file_path


@pytest.fixture
def jsonl_with_blanks(tmp_path: Path) -> Path:
    """JSONL file with blank lines interspersed."""
    file_path = tmp_path / "blanks.jsonl"
    with open(file_path, "w") as f:
        f.write(json.dumps({"type": "user", "content": "a"}) + "\n")
        f.write("\n")
        f.write("   \n")
        f.write(json.dumps({"type": "assistant", "content": "b"}) + "\n")
    return file_path


class TestReadSession:
    def test_reads_all_lines(self, sample_jsonl: Path) -> None:
        lines = read_session(str(sample_jsonl))
        assert len(lines) == 3

    def test_parses_json(self, sample_jsonl: Path) -> None:
        lines = read_session(str(sample_jsonl))
        assert lines[0]["type"] == "user"
        assert lines[1]["type"] == "assistant"
        assert lines[2]["type"] == "system"

    def test_empty_file(self, empty_jsonl: Path) -> None:
        lines = read_session(str(empty_jsonl))
        assert lines == []

    def test_skips_blank_lines(self, jsonl_with_blanks: Path) -> None:
        lines = read_session(str(jsonl_with_blanks))
        assert len(lines) == 2

    def test_preserves_order(self, sample_jsonl: Path) -> None:
        lines = read_session(str(sample_jsonl))
        assert lines[0]["uuid"] == "u1"
        assert lines[1]["uuid"] == "a1"
        assert lines[2]["uuid"] == "s1"

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            read_session("/nonexistent/path/file.jsonl")

    def test_invalid_json_skipped(self, tmp_path: Path) -> None:
        """Invalid JSON lines are silently skipped."""
        file_path = tmp_path / "invalid.jsonl"
        with open(file_path, "w") as f:
            f.write("not valid json\n")
            f.write(json.dumps({"type": "user", "uuid": "u1"}) + "\n")
            f.write("also invalid\n")
        lines = read_session(str(file_path))
        assert len(lines) == 1
        assert lines[0]["uuid"] == "u1"
