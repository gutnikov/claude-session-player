"""Integration tests with real session files."""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

from claude_session_player.models import ScreenState
from claude_session_player.parser import read_session
from claude_session_player.renderer import render


# ---------------------------------------------------------------------------
# Helper function for integration tests
# ---------------------------------------------------------------------------


def replay_session(jsonl_path: str | Path) -> str:
    """Replay a full session and return markdown output.

    Args:
        jsonl_path: Path to the JSONL session file.

    Returns:
        The markdown output from the final screen state.
    """
    lines = read_session(jsonl_path)
    state = ScreenState()
    for line in lines:
        render(state, line)
    return state.to_markdown()


# ---------------------------------------------------------------------------
# Session file paths (relative to project root)
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"

# Session files selected for snapshot testing
SESSION_FILES = {
    "simple_say_hi": EXAMPLES_DIR / "projects" / "-Users-agutnikov-work-claude-code-hub" / "37dfb8a0-c799-47ff-a4d2-015e42115815.jsonl",
    "trello_cleanup": EXAMPLES_DIR / "projects" / "-Users-agutnikov-work-trello-clone" / "930c1604-5137-4684-a344-863b511a914c.jsonl",
    "bootstrap_plugin": EXAMPLES_DIR / "projects" / "-Users-agutnikov-work-bootstrap" / "4a98b289-0b0c-4096-b36b-1cf2d5867d1f.jsonl",
    "task_with_subagent": EXAMPLES_DIR / "projects" / "-Users-agutnikov-work-ai-template" / "745a2225-3096-4339-910c-e99eaf147262.jsonl",
    "proto_migration_compaction": EXAMPLES_DIR / "projects" / "-Users-agutnikov-work-proto-migration-sme-web" / "a4ca70f0-3dc0-4bcc-a060-91f7c7054a19.jsonl",
}


# ---------------------------------------------------------------------------
# Snapshot Tests
# ---------------------------------------------------------------------------


class TestSnapshotSayHi:
    """Test simple 'say hi' session snapshot."""

    def test_simple_session_output(self):
        """Session with user→assistant text produces expected output."""
        output = replay_session(SESSION_FILES["simple_say_hi"])
        expected = read_snapshot("simple_say_hi.md")
        assert output == expected


class TestSnapshotTrelloCleanup:
    """Test Trello cleanup session with Bash tools, thinking, and multiple turns."""

    def test_trello_cleanup_output(self):
        """Session with thinking, tool use, tool results produces expected output."""
        output = replay_session(SESSION_FILES["trello_cleanup"])
        expected = read_snapshot("trello_cleanup.md")
        assert output == expected


class TestSnapshotBootstrapPlugin:
    """Test bootstrap plugin session with local command output."""

    def test_bootstrap_plugin_output(self):
        """Session with local-command-stdout produces expected output."""
        output = replay_session(SESSION_FILES["bootstrap_plugin"])
        expected = read_snapshot("bootstrap_plugin.md")
        assert output == expected


class TestSnapshotTaskSubagent:
    """Test session with Task tool and sub-agent collapsed result."""

    def test_task_subagent_output(self):
        """Session with Task tool use and collapsed result produces expected output."""
        output = replay_session(SESSION_FILES["task_with_subagent"])
        expected = read_snapshot("task_with_subagent.md")
        assert output == expected


class TestSnapshotProtoMigrationCompaction:
    """Test session with compaction mid-session."""

    def test_compaction_output(self):
        """Session with compact_boundary only shows post-compaction content."""
        output = replay_session(SESSION_FILES["proto_migration_compaction"])
        expected = read_snapshot("proto_migration_compaction.md")
        assert output == expected


def read_snapshot(filename: str) -> str:
    """Read expected output from snapshot file."""
    path = SNAPSHOTS_DIR / filename
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# No-Crash Tests
# ---------------------------------------------------------------------------


class TestNoCrash:
    """Verify all session files process without raising exceptions."""

    def test_all_sessions_no_crash(self):
        """Every real session file processes without crashing."""
        session_files = glob.glob(
            str(EXAMPLES_DIR / "projects" / "**" / "*.jsonl"), recursive=True
        )
        assert len(session_files) > 0, "No session files found"

        for path in session_files:
            # Should not raise any exception
            lines = read_session(path)
            state = ScreenState()
            for line in lines:
                render(state, line)
            # Just verify it produces some output (even if empty for metadata-only sessions)
            state.to_markdown()

    def test_subagent_files_no_crash(self):
        """Subagent session files also process without crashing."""
        subagent_files = glob.glob(
            str(EXAMPLES_DIR / "projects" / "**" / "subagents" / "*.jsonl"),
            recursive=True,
        )
        # Subagent files may or may not exist
        for path in subagent_files:
            lines = read_session(path)
            state = ScreenState()
            for line in lines:
                render(state, line)
            state.to_markdown()


# ---------------------------------------------------------------------------
# Focused Scenario Integration Tests
# ---------------------------------------------------------------------------


class TestScenarioFullTurnFlow:
    """Test full turn lifecycle: user → thinking → text → turn duration."""

    def test_full_turn_flow(self):
        """User input, thinking, text response, and turn duration render correctly."""
        lines = [
            {"type": "file-history-snapshot", "messageId": "test", "snapshot": {}},
            {
                "type": "user",
                "isMeta": False,
                "message": {"role": "user", "content": "hello"},
            },
            {
                "type": "assistant",
                "requestId": "req_1",
                "message": {
                    "content": [{"type": "thinking", "thinking": "Let me think..."}]
                },
            },
            {
                "type": "assistant",
                "requestId": "req_1",
                "message": {"content": [{"type": "text", "text": "Hi there!"}]},
            },
            {"type": "system", "subtype": "turn_duration", "durationMs": 5000},
        ]
        state = ScreenState()
        for line in lines:
            render(state, line)
        md = state.to_markdown()

        assert "❯ hello" in md
        assert "✱ Thinking…" in md
        assert "● Hi there!" in md
        assert "✱ Crunched for 5s" in md


class TestScenarioToolWithProgressAndResult:
    """Test tool call with progress updates and final result."""

    def test_tool_with_progress_and_result(self):
        """Tool call shows result (not progress) after result arrives."""
        tool_use_id = "toolu_test123"
        lines = [
            {
                "type": "assistant",
                "requestId": "req_1",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": tool_use_id,
                            "name": "Bash",
                            "input": {"command": "echo test", "description": "Echo test"},
                        }
                    ]
                },
            },
            {
                "type": "progress",
                "data": {"type": "bash_progress", "fullOutput": "testing...\nprogress line"},
                "parentToolUseID": tool_use_id,
                "toolUseID": "bash-progress-0",
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": "test output",
                            "is_error": False,
                        }
                    ]
                },
            },
        ]
        state = ScreenState()
        for line in lines:
            render(state, line)
        md = state.to_markdown()

        # Should show result, not progress
        assert "● Bash(Echo test)" in md
        assert "└ test output" in md
        # Progress should NOT appear since result overwrites it
        assert "progress line" not in md


class TestScenarioCompactionClearsHistory:
    """Test that compaction clears all pre-compaction content."""

    def test_compaction_clears_history(self):
        """Only post-compaction messages are rendered."""
        lines = [
            # Pre-compaction messages
            {
                "type": "user",
                "isMeta": False,
                "message": {"role": "user", "content": "first message"},
            },
            {
                "type": "assistant",
                "requestId": "req_1",
                "message": {"content": [{"type": "text", "text": "first response"}]},
            },
            {
                "type": "user",
                "isMeta": False,
                "message": {"role": "user", "content": "second message"},
            },
            # Compaction
            {"type": "summary", "summary": "Summary of conversation"},
            {"type": "system", "subtype": "compact_boundary"},
            # Post-compaction messages
            {
                "type": "user",
                "isMeta": False,
                "message": {"role": "user", "content": "post-compact message"},
            },
            {
                "type": "assistant",
                "requestId": "req_2",
                "message": {"content": [{"type": "text", "text": "post-compact response"}]},
            },
        ]
        state = ScreenState()
        for line in lines:
            render(state, line)
        md = state.to_markdown()

        # Pre-compaction content should NOT appear
        assert "first message" not in md
        assert "first response" not in md
        assert "second message" not in md

        # Post-compaction content should appear
        assert "❯ post-compact message" in md
        assert "● post-compact response" in md


class TestScenarioParallelToolCalls:
    """Test parallel tool calls with same requestId."""

    def test_parallel_tools(self):
        """Multiple tool_use with same requestId render correctly with matched results."""
        lines = [
            {
                "type": "assistant",
                "requestId": "req_1",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_001",
                            "name": "Read",
                            "input": {"file_path": "/path/to/file1.py"},
                        }
                    ]
                },
            },
            {
                "type": "assistant",
                "requestId": "req_1",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_002",
                            "name": "Read",
                            "input": {"file_path": "/path/to/file2.py"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_001",
                            "content": "content of file1",
                            "is_error": False,
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_002",
                            "content": "content of file2",
                            "is_error": False,
                        }
                    ]
                },
            },
        ]
        state = ScreenState()
        for line in lines:
            render(state, line)
        md = state.to_markdown()

        # Both tool calls should be rendered
        assert "● Read(file1.py)" in md
        assert "● Read(file2.py)" in md
        # Results should be matched correctly
        assert "└ content of file1" in md
        assert "└ content of file2" in md


class TestScenarioSubAgentCollapsedResult:
    """Test sub-agent Task tool with collapsed result."""

    def test_task_collapsed_result(self):
        """Task tool result uses collapsed text from toolUseResult."""
        lines = [
            {
                "type": "assistant",
                "requestId": "req_1",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_task001",
                            "name": "Task",
                            "input": {"description": "Explore the codebase"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_task001",
                            "content": [{"type": "text", "text": "Detailed full result text that is very long..."}],
                            "is_error": False,
                        }
                    ]
                },
                "toolUseResult": {
                    "status": "completed",
                    "agentId": "agent_abc",
                    "content": [{"type": "text", "text": "Summary: Found 5 modules in the codebase."}],
                    "totalDurationMs": 10000,
                },
            },
        ]
        state = ScreenState()
        for line in lines:
            render(state, line)
        md = state.to_markdown()

        assert "● Task(Explore the codebase)" in md
        # Should use collapsed result from toolUseResult
        assert "Summary: Found 5 modules" in md


class TestScenarioMultipleUserMessages:
    """Test multiple user messages across turns."""

    def test_multiple_user_messages(self):
        """Multiple user messages render with proper spacing."""
        lines = [
            {
                "type": "user",
                "isMeta": False,
                "message": {"role": "user", "content": "First question"},
            },
            {
                "type": "assistant",
                "requestId": "req_1",
                "message": {"content": [{"type": "text", "text": "First answer"}]},
            },
            {
                "type": "user",
                "isMeta": False,
                "message": {"role": "user", "content": "Second question"},
            },
            {
                "type": "assistant",
                "requestId": "req_2",
                "message": {"content": [{"type": "text", "text": "Second answer"}]},
            },
        ]
        state = ScreenState()
        for line in lines:
            render(state, line)
        md = state.to_markdown()

        # All messages should be present
        assert "❯ First question" in md
        assert "● First answer" in md
        assert "❯ Second question" in md
        assert "● Second answer" in md

        # Should have blank lines between turns (user/assistant pairs)
        lines_list = md.split("\n")
        # Check there are blank lines separating elements
        assert "" in lines_list


class TestScenarioMetadataOnlySession:
    """Test session with only metadata (no visible content)."""

    def test_metadata_only_produces_empty_output(self):
        """Session with only invisible messages produces empty output."""
        lines = [
            {"type": "file-history-snapshot", "messageId": "test", "snapshot": {}},
            {"type": "queue-operation", "operation": "dequeue"},
            {"type": "summary", "summary": "Some summary"},
        ]
        state = ScreenState()
        for line in lines:
            render(state, line)
        md = state.to_markdown()

        assert md == ""


class TestScenarioToolResultError:
    """Test tool result with error."""

    def test_tool_result_error(self):
        """Tool error renders with ✗ prefix."""
        lines = [
            {
                "type": "assistant",
                "requestId": "req_1",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_err001",
                            "name": "Bash",
                            "input": {"command": "exit 1", "description": "Fail command"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_err001",
                            "content": "Command failed with exit code 1",
                            "is_error": True,
                        }
                    ]
                },
            },
        ]
        state = ScreenState()
        for line in lines:
            render(state, line)
        md = state.to_markdown()

        assert "● Bash(Fail command)" in md
        assert "✗ Command failed" in md


class TestScenarioLocalCommandOutput:
    """Test local command stdout rendering."""

    def test_local_command_output(self):
        """Local command stdout renders as system output."""
        lines = [
            {
                "type": "user",
                "message": {
                    "content": "<local-command-stdout>Plugin installed successfully!</local-command-stdout>"
                },
            },
        ]
        state = ScreenState()
        for line in lines:
            render(state, line)
        md = state.to_markdown()

        assert "Plugin installed successfully!" in md


class TestScenarioWebSearchProgress:
    """Test WebSearch with query_update and search_results progress."""

    def test_websearch_progress(self):
        """WebSearch tool shows progress updates."""
        tool_use_id = "toolu_websearch001"
        lines = [
            {
                "type": "assistant",
                "requestId": "req_1",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": tool_use_id,
                            "name": "WebSearch",
                            "input": {"query": "Claude hooks 2026"},
                        }
                    ]
                },
            },
            {
                "type": "progress",
                "data": {"type": "query_update", "query": "Claude hooks 2026"},
                "parentToolUseID": tool_use_id,
                "toolUseID": "query-0",
            },
            {
                "type": "progress",
                "data": {"type": "search_results_received", "resultCount": 10},
                "parentToolUseID": tool_use_id,
                "toolUseID": "search-0",
            },
        ]
        state = ScreenState()
        for line in lines:
            render(state, line)
        md = state.to_markdown()

        assert "● WebSearch(Claude hooks 2026)" in md
        # Last progress should be shown (search results)
        assert "10 results" in md


# ---------------------------------------------------------------------------
# CLI Tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Tests for the CLI entry point."""

    def test_cli_produces_output(self, tmp_path, monkeypatch, capsys):
        """CLI with valid file produces markdown output."""
        import sys
        from claude_session_player.cli import main

        # Create a minimal session file
        session_file = tmp_path / "test_session.jsonl"
        session_file.write_text(
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n'
            '{"type": "assistant", "requestId": "req_1", "message": {"content": [{"type": "text", "text": "Hi!"}]}}\n'
        )

        monkeypatch.setattr(sys, "argv", ["claude-session-player", str(session_file)])

        main()
        captured = capsys.readouterr()
        assert "❯ hello" in captured.out
        assert "● Hi!" in captured.out

    def test_cli_missing_argument_shows_usage(self, monkeypatch, capsys):
        """CLI without file argument shows usage and exits with error."""
        import sys
        from claude_session_player.cli import main

        monkeypatch.setattr(sys, "argv", ["claude-session-player"])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage:" in captured.err

    def test_cli_missing_file_shows_error(self, monkeypatch, capsys):
        """CLI with non-existent file shows error and exits."""
        import sys
        from claude_session_player.cli import main

        monkeypatch.setattr(sys, "argv", ["claude-session-player", "/nonexistent/file.jsonl"])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: File not found" in captured.err

    def test_cli_module_invocation(self, tmp_path, monkeypatch, capsys):
        """CLI can be invoked via python -m claude_session_player.cli."""
        import sys
        from claude_session_player.cli import main

        # Create a minimal session file
        session_file = tmp_path / "test_session.jsonl"
        session_file.write_text(
            '{"type": "user", "message": {"role": "user", "content": "test"}}\n'
        )

        monkeypatch.setattr(sys, "argv", ["claude_session_player.cli", str(session_file)])

        main()
        captured = capsys.readouterr()
        assert "❯ test" in captured.out
