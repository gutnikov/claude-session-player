"""Tests for tool input abbreviation."""

from __future__ import annotations

from claude_session_player.tools import abbreviate_tool_input, _truncate


class TestTruncate:
    def test_short_string(self) -> None:
        assert _truncate("hello") == "hello"

    def test_exactly_60_chars(self) -> None:
        text = "a" * 60
        assert _truncate(text) == text

    def test_over_60_chars(self) -> None:
        text = "a" * 80
        result = _truncate(text)
        assert len(result) == 60
        assert result.endswith("\u2026")

    def test_custom_max_len(self) -> None:
        text = "hello world"
        result = _truncate(text, 5)
        assert result == "hell\u2026"
        assert len(result) == 5


class TestBashAbbreviation:
    def test_with_description(self) -> None:
        result = abbreviate_tool_input("Bash", {
            "command": "rm -rf node_modules && rm -rf build",
            "description": "Remove node_modules and build artifacts",
        })
        assert result == "Remove node_modules and build artifacts"

    def test_fallback_to_command(self) -> None:
        result = abbreviate_tool_input("Bash", {"command": "ls -la"})
        assert result == "ls -la"

    def test_long_description_truncated(self) -> None:
        long_desc = "A" * 80
        result = abbreviate_tool_input("Bash", {"description": long_desc})
        assert len(result) == 60
        assert result.endswith("\u2026")

    def test_empty_input(self) -> None:
        result = abbreviate_tool_input("Bash", {})
        assert result == "\u2026"


class TestFileToolAbbreviation:
    def test_read_basename(self) -> None:
        result = abbreviate_tool_input("Read", {"file_path": "/home/user/project/README.md"})
        assert result == "README.md"

    def test_write_basename(self) -> None:
        result = abbreviate_tool_input("Write", {"file_path": "/tmp/.gitignore"})
        assert result == ".gitignore"

    def test_edit_basename(self) -> None:
        result = abbreviate_tool_input("Edit", {"file_path": "/src/config.py"})
        assert result == "config.py"

    def test_missing_file_path(self) -> None:
        result = abbreviate_tool_input("Read", {})
        assert result == "\u2026"


class TestGlobAbbreviation:
    def test_short_pattern(self) -> None:
        result = abbreviate_tool_input("Glob", {"pattern": "**/*.ts"})
        assert result == "**/*.ts"

    def test_long_pattern(self) -> None:
        long_pattern = "src/**/" + "a" * 80 + "/*.ts"
        result = abbreviate_tool_input("Glob", {"pattern": long_pattern})
        assert len(result) == 60
        assert result.endswith("\u2026")


class TestGrepAbbreviation:
    def test_simple_pattern(self) -> None:
        result = abbreviate_tool_input("Grep", {"pattern": "TODO"})
        assert result == "TODO"


class TestTaskAbbreviation:
    def test_with_description(self) -> None:
        result = abbreviate_tool_input("Task", {"description": "Explore codebase structure"})
        assert result == "Explore codebase structure"

    def test_long_description(self) -> None:
        long_desc = "X" * 80
        result = abbreviate_tool_input("Task", {"description": long_desc})
        assert len(result) == 60


class TestWebSearchAbbreviation:
    def test_query(self) -> None:
        result = abbreviate_tool_input("WebSearch", {"query": "Claude hooks 2026"})
        assert result == "Claude hooks 2026"


class TestWebFetchAbbreviation:
    def test_url(self) -> None:
        result = abbreviate_tool_input("WebFetch", {"url": "https://example.com/page"})
        assert result == "https://example.com/page"


class TestUnknownToolAbbreviation:
    def test_unknown_tool(self) -> None:
        result = abbreviate_tool_input("NotebookEdit", {"notebook_path": "/path/to/nb.ipynb"})
        assert result == "\u2026"

    def test_unknown_tool_with_input(self) -> None:
        result = abbreviate_tool_input("CustomTool", {"param": "value"})
        assert result == "\u2026"
