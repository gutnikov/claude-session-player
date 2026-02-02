"""Tests for tool input abbreviation logic."""

from __future__ import annotations

from claude_session_player.tools import _basename, _truncate, abbreviate_tool_input


class TestTruncate:
    """Tests for the _truncate helper."""

    def test_short_text(self) -> None:
        assert _truncate("hello") == "hello"

    def test_exact_60(self) -> None:
        text = "a" * 60
        assert _truncate(text) == text

    def test_61_chars_truncated(self) -> None:
        text = "a" * 61
        result = _truncate(text)
        assert len(result) == 60
        assert result.endswith("\u2026")

    def test_long_text(self) -> None:
        text = "x" * 100
        result = _truncate(text)
        assert len(result) == 60
        assert result == "x" * 59 + "\u2026"


class TestBasename:
    """Tests for the _basename helper."""

    def test_full_path(self) -> None:
        assert _basename("/Users/agutnikov/work/project/README.md") == "README.md"

    def test_basename_only(self) -> None:
        assert _basename("README.md") == "README.md"

    def test_relative_path(self) -> None:
        assert _basename("src/main.py") == "main.py"

    def test_trailing_slash(self) -> None:
        # Edge case: trailing slash gives empty string
        assert _basename("src/") == ""


class TestAbbreviateBash:
    """Tests for Bash tool abbreviation."""

    def test_with_description(self) -> None:
        result = abbreviate_tool_input("Bash", {
            "command": "rm -rf node_modules",
            "description": "Remove node_modules and build artifacts",
        })
        assert result == "Remove node_modules and build artifacts"

    def test_without_description(self) -> None:
        result = abbreviate_tool_input("Bash", {
            "command": "git status && git diff HEAD",
        })
        assert result == "git status && git diff HEAD"

    def test_long_command_truncated(self) -> None:
        long_cmd = "find . -name '*.py' -exec grep -l 'TODO' {} \\; | sort | uniq -c | sort -rn | head -20"
        result = abbreviate_tool_input("Bash", {"command": long_cmd})
        assert len(result) == 60
        assert result.endswith("\u2026")

    def test_long_description_truncated(self) -> None:
        long_desc = "Remove all temporary files and build artifacts from the project directory tree recursively"
        result = abbreviate_tool_input("Bash", {
            "command": "rm -rf tmp/",
            "description": long_desc,
        })
        assert len(result) == 60
        assert result.endswith("\u2026")


class TestAbbreviateFilePaths:
    """Tests for Read, Write, Edit, NotebookEdit basename extraction."""

    def test_read_full_path(self) -> None:
        result = abbreviate_tool_input("Read", {"file_path": "/Users/user/project/README.md"})
        assert result == "README.md"

    def test_read_basename_only(self) -> None:
        result = abbreviate_tool_input("Read", {"file_path": "README.md"})
        assert result == "README.md"

    def test_write_path(self) -> None:
        result = abbreviate_tool_input("Write", {"file_path": "/src/config.py", "content": "x = 1"})
        assert result == "config.py"

    def test_edit_path(self) -> None:
        result = abbreviate_tool_input("Edit", {"file_path": "/a/b/c/models.py"})
        assert result == "models.py"

    def test_notebook_edit_path(self) -> None:
        result = abbreviate_tool_input("NotebookEdit", {"notebook_path": "/home/user/analysis.ipynb"})
        assert result == "analysis.ipynb"


class TestAbbreviatePatterns:
    """Tests for Glob, Grep pattern abbreviation."""

    def test_glob_pattern(self) -> None:
        result = abbreviate_tool_input("Glob", {"pattern": "**/*.ts"})
        assert result == "**/*.ts"

    def test_grep_pattern(self) -> None:
        result = abbreviate_tool_input("Grep", {"pattern": "TODO"})
        assert result == "TODO"

    def test_grep_long_pattern_truncated(self) -> None:
        long_pattern = "very_long_function_name_that_exceeds_the_sixty_character_limit_for_display"
        result = abbreviate_tool_input("Grep", {"pattern": long_pattern})
        assert len(result) == 60
        assert result.endswith("\u2026")


class TestAbbreviateOtherTools:
    """Tests for Task, WebSearch, WebFetch, TodoWrite, unknown."""

    def test_task_description(self) -> None:
        result = abbreviate_tool_input("Task", {"description": "Explore codebase structure"})
        assert result == "Explore codebase structure"

    def test_task_long_description(self) -> None:
        long_desc = "Explore the entire codebase structure and identify all modules that need refactoring"
        result = abbreviate_tool_input("Task", {"description": long_desc})
        assert len(result) == 60
        assert result.endswith("\u2026")

    def test_websearch_query(self) -> None:
        result = abbreviate_tool_input("WebSearch", {"query": "Claude hooks 2026"})
        assert result == "Claude hooks 2026"

    def test_webfetch_url(self) -> None:
        result = abbreviate_tool_input("WebFetch", {"url": "https://example.com/docs"})
        assert result == "https://example.com/docs"

    def test_todowrite_fixed(self) -> None:
        result = abbreviate_tool_input("TodoWrite", {"todos": [{"content": "item"}]})
        assert result == "todos"

    def test_todowrite_empty_input(self) -> None:
        result = abbreviate_tool_input("TodoWrite", {})
        assert result == "todos"

    def test_unknown_tool(self) -> None:
        result = abbreviate_tool_input("SomeNewTool", {"foo": "bar"})
        assert result == "\u2026"


class TestAbbreviateEdgeCases:
    """Tests for edge cases in abbreviation."""

    def test_empty_input_dict(self) -> None:
        result = abbreviate_tool_input("Bash", {})
        assert result == "\u2026"

    def test_missing_expected_field(self) -> None:
        result = abbreviate_tool_input("Read", {"some_other_field": "value"})
        assert result == "\u2026"

    def test_empty_string_field(self) -> None:
        result = abbreviate_tool_input("Bash", {"command": "", "description": ""})
        assert result == "\u2026"

    def test_bash_empty_description_falls_back(self) -> None:
        result = abbreviate_tool_input("Bash", {"command": "ls", "description": ""})
        assert result == "ls"
